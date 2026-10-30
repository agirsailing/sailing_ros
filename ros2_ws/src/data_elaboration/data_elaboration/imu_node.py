"""Estimate or pass through robotic attitude, complete the aero world conversion, publish TF.

A fusing IMU (BNO085) supplies orientation; it is passed through unchanged.
Raw 6-DOF input (orientation_covariance[0] == -1) still uses the complementary filter.
"""

import copy
import math
import time
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster
from sail_common.freshness import is_fresh

from data_elaboration.generated.ros_endpoints import Topics
from data_elaboration.processing.imu_filter import ImuFilter
from data_elaboration.processing.lever_arm import LeverArmCompensator
from data_elaboration.processing.imu_frames import (
    multiply, quaternion_from_degrees, rotation_matrix, rotate_covariance,
)


class ImuNode(Node):
    def __init__(self):
        super().__init__('imu_node')

        # 1. Declare and read parameters.
        self.calibration_samples = self.declare_parameter('calibration_samples', Parameter.Type.INTEGER).value
        self.gravity_mps2 = self.declare_parameter('gravity_mps2', Parameter.Type.DOUBLE).value
        self.complementary_alpha = self.declare_parameter('complementary_alpha', Parameter.Type.DOUBLE).value
        self.max_sample_dt_s = self.declare_parameter('max_sample_dt_s', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value
        self.max_sample_age_s = self.declare_parameter('max_sample_age_s', Parameter.Type.DOUBLE).value
        self.publish_rate_hz = self.declare_parameter('publish_rate_hz', Parameter.Type.DOUBLE).value

        self.frame_base = self.declare_parameter('frame_base', Parameter.Type.STRING).value
        self.frame_imu = self.declare_parameter('frame_imu', Parameter.Type.STRING).value
        self.frame_robotic = self.declare_parameter('frame_robotic', Parameter.Type.STRING).value
        self.frame_aero = self.declare_parameter('frame_aero', Parameter.Type.STRING).value
        self.tf_offset = self.declare_parameter('tf_offset', Parameter.Type.DOUBLE_ARRAY).value
        self.tf_offset_aero = self.declare_parameter('tf_offset_aero', Parameter.Type.DOUBLE_ARRAY).value
        self.world_rotation_rpy_deg = self.declare_parameter('world_rotation_rpy_deg', Parameter.Type.DOUBLE_ARRAY).value
        self.cov_orient = self.declare_parameter('cov_orient', Parameter.Type.DOUBLE).value
        self.cov_vel = self.declare_parameter('cov_vel', Parameter.Type.DOUBLE).value
        self.cov_acc = self.declare_parameter('cov_acc', Parameter.Type.DOUBLE).value

        # 2. Validate configuration and initialize the estimator.
        self._validate_parameters()
        self.filter = ImuFilter(
            self.calibration_samples,
            self.gravity_mps2,
            self.complementary_alpha,
            self.max_sample_dt_s
        )
        self.lever_arm = LeverArmCompensator(self.tf_offset[:3], self.max_sample_dt_s)

        # Complete the aerodynamic world conversion after the body transformer.
        self.world_quaternion = quaternion_from_degrees(*self.world_rotation_rpy_deg)
        self.world_rotation = rotation_matrix(self.world_quaternion)
        self.aero_last_stamp = None
        self._robotic_last_stamp = None
        self._last_clock_ns = None
        self._robotic_sample = None

        # 3. Standard processed IMU publishers; web angles are derived by the gateway.
        self.imu_pub = self.create_publisher(
            Imu,
            Topics.IMU_NODE.PUB.IMU,
            self.qos_depth
        )
        self.aero_imu_pub = self.create_publisher(
            Imu, Topics.IMU_NODE.PUB.IMU_AERO, self.qos_depth)
        # Sensor pose is physical; processed frames are colocated at base_link/COM.
        self.tf_broadcaster = StaticTransformBroadcaster(self)
        self._publish_static_frames()

        # 4. Consume the real imu_transformer output; mounting is already corrected.
        self.imu_sub = self.create_subscription(
            Imu,
            Topics.IMU_NODE.SUB.IMU,
            self.publish_attitude,
            self.qos_depth
        )
        self.aero_imu_sub = self.create_subscription(
            Imu, Topics.IMU_NODE.SUB.IMU_AERO, self.publish_aero, self.qos_depth)
        # Orientation processing always runs on new input. Periodic mode
        # throttles only the robotic output; the aero branch follows that output
        # immediately, avoiding a second timer delay in the conversion chain.
        self.publish_timer = None
        if self.publish_rate_hz > 0:
            self.publish_timer = self.create_timer(1.0 / self.publish_rate_hz, self.publish_latest)
        if self.calibration_samples:
            self.get_logger().info(
                f'Raw 6-DOF fallback calibration uses {self.calibration_samples} samples; '
                'sensor-fused orientation bypasses this calibration'
            )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        if not math.isfinite(self.max_sample_age_s) or self.max_sample_age_s <= 0:
            raise ValueError('max_sample_age_s must be finite and positive')
        if not math.isfinite(self.publish_rate_hz) or self.publish_rate_hz < 0:
            raise ValueError('publish_rate_hz must be finite and nonnegative')
        if self.calibration_samples < 0:
            raise ValueError('calibration_samples must not be negative')
        if not math.isfinite(self.gravity_mps2) or self.gravity_mps2 <= 0:
            raise ValueError('gravity_mps2 must be finite and positive')
        if not 0 <= self.complementary_alpha <= 1:
            raise ValueError('complementary_alpha must be between 0 and 1')
        if not math.isfinite(self.max_sample_dt_s) or self.max_sample_dt_s <= 0:
            raise ValueError('max_sample_dt_s must be finite and positive')
        frames = (self.frame_base, self.frame_imu, self.frame_robotic, self.frame_aero)
        if any(not name.strip() for name in frames) or len(set(frames)) != len(frames):
            raise ValueError('Base, input IMU, robotic and aero frame IDs must be distinct and nonempty')
        for offset in (self.tf_offset, self.tf_offset_aero):
            if len(offset) != 6 or not all(math.isfinite(v) for v in offset):
                raise ValueError('TF offsets must be [x, y, z, roll, pitch, yaw], metres/degrees')
        # FRD is a convention, not an arbitrary mounting rotation.
        aero = rotation_matrix(quaternion_from_degrees(*self.tf_offset_aero[3:]))
        expected = ((1, 0, 0), (0, -1, 0), (0, 0, -1))
        if (any(v != 0 for v in self.tf_offset_aero[:3])
                or any(not math.isclose(aero[i][j], expected[i][j], abs_tol=1e-9)
                       for i in range(3) for j in range(3))):
            raise ValueError('tf_offset_aero must represent colocated FLU-to-FRD axes (180 deg roll)')
        if any(not math.isfinite(v) or v < 0 for v in (self.cov_orient, self.cov_vel, self.cov_acc)):
            raise ValueError('Covariance diagonals must be finite and nonnegative')
        if (len(self.world_rotation_rpy_deg) != 3
                or not all(math.isfinite(v) for v in self.world_rotation_rpy_deg)):
            raise ValueError('world_rotation_rpy_deg must contain three finite angles')
        # The world change must turn world-up into world-down (roll 180, pitch 0).
        # Its yaw only re-labels the horizontal axes: 90 degrees turns ENU into NED.
        rotation = rotation_matrix(quaternion_from_degrees(*self.world_rotation_rpy_deg))
        if any(not math.isclose(rotation[2][j], (0, 0, -1)[j], abs_tol=1e-9) for j in range(3)):
            raise ValueError('world_rotation_rpy_deg must map world-up to world-down: '
                             'roll 180, pitch 0 (yaw 90 converts ENU to NED)')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    def _publish_static_frames(self):
        transforms = []
        # imu_transformer rotates vectors only. The callback below transfers
        # acceleration to the COM before publishing in the processed frames.
        offsets = (
            (self.frame_base, self.frame_imu, self.tf_offset),
            (self.frame_base, self.frame_robotic, [0.0] * 6),
            (self.frame_robotic, self.frame_aero, self.tf_offset_aero),
        )
        for parent, child, offset in offsets:
            transform = TransformStamped()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = parent
            transform.child_frame_id = child
            transform.transform.translation.x = offset[0]
            transform.transform.translation.y = offset[1]
            transform.transform.translation.z = offset[2]
            q = quaternion_from_degrees(*offset[3:])
            transform.transform.rotation.x = q[0]
            transform.transform.rotation.y = q[1]
            transform.transform.rotation.z = q[2]
            transform.transform.rotation.w = q[3]
            transforms.append(transform)
        self.tf_broadcaster.sendTransform(transforms)

    @staticmethod
    def _diagonal(value):
        return [value, 0.0, 0.0, 0.0, value, 0.0, 0.0, 0.0, value]

    # -----------------------
    #   Estimate and publish orientation
    # -----------------------
    def _now(self):
        now = self.get_clock().now()
        if self._last_clock_ns is not None and now.nanoseconds < self._last_clock_ns:
            self.filter.reset()
            self.lever_arm.reset()
            self._robotic_last_stamp = None
            self._robotic_sample = None
            self.aero_last_stamp = None
        self._last_clock_ns = now.nanoseconds
        return now

    def _store_robotic(self, output):
        self._robotic_sample = (output, time.monotonic())
        if self.publish_rate_hz == 0:
            self.publish_latest()

    def publish_latest(self):
        now = self._now()
        if self._robotic_sample is None:
            return
        output, received_at = self._robotic_sample
        if (is_fresh(output.header.stamp, now, self.max_sample_age_s)
                and is_fresh(received_at, time.monotonic(), self.max_sample_age_s)):
            self.imu_pub.publish(output)

    def publish_attitude(self, msg):
        now = self._now()
        if not is_fresh(msg.header.stamp, now, self.max_sample_age_s):
            return
        if (msg.header.frame_id != self.frame_robotic
                or msg.linear_acceleration_covariance[0] == -1
                or msg.angular_velocity_covariance[0] == -1):
            return
        stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        if self._robotic_last_stamp is not None and stamp_ns <= self._robotic_last_stamp:
            return
        if not all(math.isfinite(v) for v in (
                msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z,
                msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z)):
            return
        if msg.orientation_covariance[0] != -1:
            norm = math.hypot(msg.orientation.x, msg.orientation.y,
                              msg.orientation.z, msg.orientation.w)
            if not math.isfinite(norm) or norm == 0:
                return
        self._robotic_last_stamp = stamp_ns
        acceleration = self.lever_arm.update(
            stamp_ns,
            (msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z),
            (msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z))
        if acceleration is None:
            # Nonzero lever arm needs two consecutive samples. Do not publish
            # uncorrected data as COM acceleration at startup or after a gap.
            self._robotic_sample = None
            return
        if self.lever_arm.enabled:
            msg = copy.deepcopy(msg)
            msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z = acceleration
            # Original sensor covariance excludes gyro/derivative uncertainty.
            # Zero denotes unknown; a positive override describes corrected data.
            msg.linear_acceleration_covariance = self._diagonal(self.cov_acc)
        if msg.orientation_covariance[0] != -1:
            # A fusing IMU (BNO085) already estimated orientation: do not refilter.
            self._publish_fused(msg)
            return
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        acceleration = (
            msg.linear_acceleration.x,
            msg.linear_acceleration.y,
            msg.linear_acceleration.z
        )
        angular_velocity = (
            msg.angular_velocity.x,
            msg.angular_velocity.y,
            msg.angular_velocity.z
        )
        result = self.filter.update(stamp, acceleration, angular_velocity)
        if result is None:
            return
        acceleration, angular_velocity, quaternion = result

        output = copy.deepcopy(msg)
        output.header.frame_id = self.frame_robotic
        output.linear_acceleration.x = acceleration[0]
        output.linear_acceleration.y = acceleration[1]
        output.linear_acceleration.z = acceleration[2]
        output.angular_velocity.x = angular_velocity[0]
        output.angular_velocity.y = angular_velocity[1]
        output.angular_velocity.z = angular_velocity[2]
        output.orientation.x = quaternion[0]
        output.orientation.y = quaternion[1]
        output.orientation.z = quaternion[2]
        output.orientation.w = quaternion[3]
        # Zero means unknown uncertainty until the YAML covariances are calibrated.
        output.orientation_covariance = self._diagonal(self.cov_orient)
        output.angular_velocity_covariance = self._diagonal(self.cov_vel)
        output.linear_acceleration_covariance = self._diagonal(self.cov_acc)

        self._store_robotic(output)

    # Pass through sensor-fused orientation (ENU world for the BNO085 rotation vector).
    def _publish_fused(self, msg):
        q = msg.orientation
        quaternion = (q.x, q.y, q.z, q.w)
        norm = math.hypot(*quaternion)
        if not math.isfinite(norm) or norm == 0:
            return False
        quaternion = tuple(v / norm for v in quaternion)
        output = copy.deepcopy(msg)
        output.header.frame_id = self.frame_robotic
        output.orientation.x, output.orientation.y, output.orientation.z, output.orientation.w = quaternion
        # Keep the sensor's covariance unless YAML supplies a characterized value.
        for field, value in (('orientation_covariance', self.cov_orient),
                             ('angular_velocity_covariance', self.cov_vel),
                             ('linear_acceleration_covariance', self.cov_acc)):
            if value > 0:
                setattr(output, field, self._diagonal(value))

        self._store_robotic(output)
        return True

    # Complete only the world-reference conversion after the aero transformer.
    def publish_aero(self, msg):
        if not is_fresh(msg.header.stamp, self._now(), self.max_sample_age_s):
            return
        if msg.header.frame_id != self.frame_aero or msg.orientation_covariance[0] == -1:
            return
        q = msg.orientation
        quaternion = (q.x, q.y, q.z, q.w)
        norm = math.hypot(*quaternion)
        if not math.isfinite(norm) or norm == 0:
            return
        stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        if self.aero_last_stamp is not None and stamp <= self.aero_last_stamp:
            return
        # Body vectors and their covariance were already transformed by the ROS node.
        # Only orientation and its world-referenced covariance need this left product.
        transformed = multiply(self.world_quaternion, tuple(v / norm for v in quaternion))
        output = copy.deepcopy(msg)
        output.orientation.x, output.orientation.y, output.orientation.z, output.orientation.w = transformed
        output.orientation_covariance = rotate_covariance(self.world_rotation, msg.orientation_covariance)

        self.aero_last_stamp = stamp
        self.aero_imu_pub.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ImuNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
