"""Select a navigation direction from receiver course or magnetic bearing.

GPS course describes motion over ground, not necessarily the bow direction.
This preserves the existing speed-based selection; it is not attitude fusion.
"""

import copy
import math
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from geometry_msgs.msg import Vector3Stamped
from sail_msgs.msg import GpsData, GpsSummary
from std_msgs.msg import Float64

from sensors.generated.ros_endpoints import Topics as SensorTopics
from data_elaboration.generated.ros_endpoints import Topics
from data_elaboration.processing.heading import choose_navigation_direction


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


class HeadingNode(Node):
    def __init__(self):
        super().__init__('heading_node')

        # 1. Declare and read parameters.
        self.rate_hz = self.declare_parameter('rate_hz', Parameter.Type.DOUBLE).value
        self.speed_threshold = self.declare_parameter('gps_speed_threshold_mps', Parameter.Type.DOUBLE).value
        self.max_input_age_s = self.declare_parameter('max_input_age_s', Parameter.Type.DOUBLE).value
        self.compass_x_sign = self.declare_parameter('compass_x_sign', Parameter.Type.DOUBLE).value
        self.compass_y_sign = self.declare_parameter('compass_y_sign', Parameter.Type.DOUBLE).value
        self.compass_x_bias = self.declare_parameter('compass_x_bias', Parameter.Type.DOUBLE).value
        self.compass_y_bias = self.declare_parameter('compass_y_bias', Parameter.Type.DOUBLE).value
        self.heading_offset_deg = self.declare_parameter('heading_offset_deg', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration and initialize input state.
        self._validate_parameters()
        self.gps = None
        self.compass = None
        self.last_now = None

        # 3. Processing publishers.
        self.heading_pub = self.create_publisher(
            Float64,
            Topics.HEADING_NODE.PUB.HEADING_DEG,
            self.qos_depth
        )
        self.summary_pub = self.create_publisher(
            GpsSummary,
            Topics.HEADING_NODE.PUB.GPS_SUMMARY,
            self.qos_depth
        )

        # 4. Raw sensor subscriptions and processing timer.
        self.gps_sub = self.create_subscription(
            GpsData,
            SensorTopics.GPS_NODE.PUB.GPS_DATA,
            self.receive_gps,
            self.qos_depth
        )
        self.compass_sub = self.create_subscription(
            Vector3Stamped,
            SensorTopics.I2C_SENSORS_NODE.PUB.COMPASS_DATA,
            self.receive_compass,
            self.qos_depth
        )
        self.heading_timer = self.create_timer(
            1.0 / self.rate_hz,
            self.publish_heading
        )

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        if not math.isfinite(self.rate_hz) or self.rate_hz <= 0:
            raise ValueError('rate_hz must be finite and positive')
        if not math.isfinite(self.max_input_age_s) or self.max_input_age_s <= 0:
            raise ValueError('max_input_age_s must be finite and positive')
        if not math.isfinite(self.speed_threshold) or self.speed_threshold <= 0:
            raise ValueError('gps_speed_threshold_mps must be finite and positive')
        if self.compass_x_sign not in (-1.0, 1.0) or self.compass_y_sign not in (-1.0, 1.0):
            raise ValueError('Compass axis signs must be -1.0 or 1.0')
        if not all(math.isfinite(v) for v in (
                self.compass_x_bias, self.compass_y_bias, self.heading_offset_deg)):
            raise ValueError('Compass biases and heading offset must be finite')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    def receive_gps(self, msg):
        self.gps = msg

    def receive_compass(self, msg):
        self.compass = msg

    # -----------------------
    #   Select and publish the navigation direction
    # -----------------------
    def publish_heading(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        if self.last_now is not None and now < self.last_now:
            self.gps = None
            self.compass = None
        self.last_now = now

        gps = None
        if self.gps is not None:
            gps = (
                seconds(self.gps.header.stamp), self.gps.fix_valid,
                self.gps.ground_speed_mps, self.gps.course_deg
            )
        compass = None
        if self.compass is not None:
            compass = (
                seconds(self.compass.header.stamp),
                self.compass.vector.x, self.compass.vector.y
            )
        heading, source, _ = choose_navigation_direction(
            gps, compass, now, self.max_input_age_s, self.speed_threshold,
            self.compass_x_sign, self.compass_y_sign,
            self.compass_x_bias, self.compass_y_bias, self.heading_offset_deg
        )

        direction = Float64()
        direction.data = heading
        self.heading_pub.publish(direction)

        self.publish_summary(heading, source, now)

    def publish_summary(self, heading, source, now):
        summary = GpsSummary()
        summary.header.stamp = self.get_clock().now().to_msg()
        summary.latitude_deg = float('nan')
        summary.longitude_deg = float('nan')
        summary.sog_mps = float('nan')
        summary.fix_valid = False
        if self.gps is not None:
            summary.gps_stamp = copy.deepcopy(self.gps.header.stamp)
            summary.header.frame_id = self.gps.header.frame_id
            summary.fix_valid = (
                self.gps.fix_valid
                and 0 <= now - seconds(self.gps.header.stamp) <= self.max_input_age_s
                and all(math.isfinite(v) for v in (
                    self.gps.latitude_deg, self.gps.longitude_deg,
                    self.gps.ground_speed_mps))
            )
            if summary.fix_valid:
                summary.latitude_deg = self.gps.latitude_deg
                summary.longitude_deg = self.gps.longitude_deg
                summary.sog_mps = self.gps.ground_speed_mps

        summary.direction_deg = heading
        summary.direction_valid = math.isfinite(heading)
        summary.direction_source = GpsSummary.DIRECTION_NONE
        if source == 'gps':
            summary.direction_source = GpsSummary.DIRECTION_GPS_COG
            summary.direction_stamp = copy.deepcopy(self.gps.header.stamp)
        elif source == 'compass':
            summary.direction_source = GpsSummary.DIRECTION_COMPASS
            summary.direction_stamp = copy.deepcopy(self.compass.header.stamp)
        self.summary_pub.publish(summary)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = HeadingNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
