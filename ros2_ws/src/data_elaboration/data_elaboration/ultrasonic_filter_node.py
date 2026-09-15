"""Estimate waterline-reference height from left/right bow ranges and attitude."""

from collections import deque
import copy
import math

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu, Range
from sail_msgs.msg import BoatHeight

from sensors.generated.ros_endpoints import Topics as SensorTopics
from data_elaboration.generated.ros_endpoints import Topics
from data_elaboration.processing.boat_height import (
    beam_direction, fuse_estimates, project_height, vertical_row,
)


class UltrasonicFilterNode(Node):
    def __init__(self):
        super().__init__('ultrasonic_filter_node')

        # 1. Mounting coordinates, angles and timing come from this package's YAML.
        self.left_position_m = self.declare_parameter('left.position_m', Parameter.Type.DOUBLE_ARRAY).value
        self.left_lateral_deg = self.declare_parameter('left.lateral_tilt_deg', Parameter.Type.DOUBLE).value
        self.left_forward_deg = self.declare_parameter('left.forward_tilt_deg', Parameter.Type.DOUBLE).value
        self.left_frame_id = self.declare_parameter('left.frame_id', Parameter.Type.STRING).value
        self.right_position_m = self.declare_parameter('right.position_m', Parameter.Type.DOUBLE_ARRAY).value
        self.right_lateral_deg = self.declare_parameter('right.lateral_tilt_deg', Parameter.Type.DOUBLE).value
        self.right_forward_deg = self.declare_parameter('right.forward_tilt_deg', Parameter.Type.DOUBLE).value
        self.right_frame_id = self.declare_parameter('right.frame_id', Parameter.Type.STRING).value
        self.attitude_frame_id = self.declare_parameter('attitude_frame_id', Parameter.Type.STRING).value
        self.reference_frame_id = self.declare_parameter('reference_frame_id', Parameter.Type.STRING).value
        self.max_range_age_s = self.declare_parameter('max_range_age_s', Parameter.Type.DOUBLE).value
        self.max_attitude_age_s = self.declare_parameter('max_attitude_age_s', Parameter.Type.DOUBLE).value
        self.max_pair_dt_s = self.declare_parameter('max_pair_dt_s', Parameter.Type.DOUBLE).value
        self.max_incidence_deg = self.declare_parameter('max_incidence_deg', Parameter.Type.DOUBLE).value
        self.incidence_weight_power = self.declare_parameter('incidence_weight_power', Parameter.Type.DOUBLE).value
        self.max_disagreement_m = self.declare_parameter('max_disagreement_m', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration and prepare fixed mounting geometry.
        self._validate_parameters()
        self.positions = {'left': self.left_position_m, 'right': self.right_position_m}
        self.beams = {
            'left': beam_direction(self.left_lateral_deg, self.left_forward_deg),
            'right': beam_direction(self.right_lateral_deg, self.right_forward_deg),
        }
        self.frames = {'left': self.left_frame_id, 'right': self.right_frame_id}
        self.min_downward_cosine = math.cos(math.radians(self.max_incidence_deg))
        self.attitudes = deque()
        self.estimates = {}
        self.last_range_stamps = {}
        self.last_now = None

        # 3. Publish a single height referred to the configured waterline point.
        self.height_pub = self.create_publisher(
            BoatHeight, Topics.ULTRASONIC_FILTER_NODE.PUB.HEIGHT, self.qos_depth)

        # 4. Orientation and independent range subscriptions.
        self.attitude_sub = self.create_subscription(
            Imu, Topics.IMU_NODE.PUB.IMU, self.receive_attitude, self.qos_depth)
        self.left_sub = self.create_subscription(
            Range, SensorTopics.ULTRASONIC_LEFT_NODE.PUB.RANGE,
            self.receive_left, self.qos_depth)
        self.right_sub = self.create_subscription(
            Range, SensorTopics.ULTRASONIC_RIGHT_NODE.PUB.RANGE,
            self.receive_right, self.qos_depth)

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        for position in (self.left_position_m, self.right_position_m):
            if len(position) != 3 or not all(math.isfinite(v) for v in position):
                raise ValueError('Each position_m must contain three finite FLU coordinates')
        for angle in (self.left_lateral_deg, self.right_lateral_deg,
                      self.left_forward_deg, self.right_forward_deg):
            if not math.isfinite(angle) or not -90 < angle < 90:
                raise ValueError('Mounting tilts must lie strictly between -90 and 90 degrees')
        for value in (self.max_range_age_s, self.max_attitude_age_s,
                      self.max_pair_dt_s, self.max_disagreement_m):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Timing limits and max_disagreement_m must be finite and positive')
        if not 0 < self.max_incidence_deg < 90:
            raise ValueError('max_incidence_deg must lie strictly between 0 and 90')
        if not 0 <= self.incidence_weight_power <= 64:
            raise ValueError('incidence_weight_power must lie between 0 and 64')
        if self.max_pair_dt_s > self.max_range_age_s:
            raise ValueError('max_pair_dt_s must not exceed max_range_age_s')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if not all(frame.strip() for frame in (
                self.left_frame_id, self.right_frame_id,
                self.attitude_frame_id, self.reference_frame_id)):
            raise ValueError('Frame IDs must not be empty')

    @staticmethod
    def _stamp(msg):
        return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

    def _now(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        if self.last_now is not None and now < self.last_now:
            # Do not combine samples from different bag loops / clock epochs.
            self.attitudes.clear()
            self.estimates.clear()
            self.last_range_stamps.clear()
        self.last_now = now
        history_s = self.max_range_age_s + self.max_attitude_age_s
        while self.attitudes and now - self.attitudes[0][0] > history_s:
            self.attitudes.popleft()
        return now

    # Keep a short orientation history to correct each range at its own timestamp.
    def receive_attitude(self, msg):
        now = self._now()
        stamp = self._stamp(msg)
        if not 0 <= now - stamp <= self.max_range_age_s + self.max_attitude_age_s:
            return
        if self.attitudes and stamp <= self.attitudes[-1][0]:
            return
        if msg.header.frame_id != self.attitude_frame_id or msg.orientation_covariance[0] == -1:
            self.attitudes.clear()
            self.estimates.clear()
            return
        q = msg.orientation
        up = vertical_row((q.x, q.y, q.z, q.w))
        if up is None:
            self.attitudes.clear()
            self.estimates.clear()
            return
        self.attitudes.append((stamp, up))

    def receive_left(self, msg):
        self._receive_range('left', msg)

    def receive_right(self, msg):
        self._receive_range('right', msg)

    def _receive_range(self, side, msg):
        now = self._now()
        stamp = self._stamp(msg)
        if stamp <= self.last_range_stamps.get(side, -math.inf):
            return
        if not 0 <= now - stamp <= self.max_range_age_s:
            return
        self.last_range_stamps[side] = stamp
        # A new invalid reading invalidates that side's previous candidate.
        self.estimates.pop(side, None)
        if msg.header.frame_id != self.frames[side]:
            return
        attitude = next((up for t, up in reversed(self.attitudes)
                         if 0 <= stamp - t <= self.max_attitude_age_s), None)
        if attitude is None:
            return
        estimate = project_height(
            msg.range, msg.min_range, msg.max_range,
            self.positions[side], self.beams[side], attitude, stamp,
            self.min_downward_cosine)
        if estimate is None:
            return
        self.estimates[side] = estimate

        # Fuse corrected heights only when their measurement times are close.
        candidates = [
            item for item in self.estimates.values()
            if 0 <= now - item.stamp_s <= self.max_range_age_s
            and abs(stamp - item.stamp_s) <= self.max_pair_dt_s
        ]
        height = fuse_estimates(
            candidates, self.incidence_weight_power, self.max_disagreement_m)
        if height is None:
            self.get_logger().warning('Conflicting ultrasonic heights with equal incidence')
            return
        output = BoatHeight()
        # The scalar is a world-vertical clearance at this boat-fixed reference.
        output.header = copy.deepcopy(msg.header)
        output.header.frame_id = self.reference_frame_id
        output.height_m = height
        self.height_pub.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UltrasonicFilterNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
