"""Estimate robotic attitude, complete the aero world conversion and publish TF."""

import copy
import math
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster
from sail_msgs.msg import RollPitchYaw

from data_elaboration.generated.ros_endpoints import Topics
from data_elaboration.processing.imu_filter import ImuFilter
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

        # Track aerodynamic yaw independently from the robotic filter.
        self.world_quaternion = quaternion_from_degrees(*self.world_rotation_rpy_deg)
        self.world_rotation = rotation_matrix(self.world_quaternion)
        self.aero_last_stamp = None
        self.aero_last_yaw = None
        self.aero_continuous_yaw = 0.0

        # 3. Processed IMU and explicit angle publishers.
        self.imu_pub = self.create_publisher(
            Imu,
            Topics.IMU_NODE.PUB.IMU,
            self.qos_depth
        )
        self.rpy_pub = self.create_publisher(
            RollPitchYaw,
            Topics.IMU_NODE.PUB.RPY,
            self.qos_depth
        )

        self.aero_imu_pub = self.create_publisher(
            Imu, Topics.IMU_NODE.PUB.IMU_AERO, self.qos_depth)
        self.aero_rpy_pub = self.create_publisher(
            RollPitchYaw, Topics.IMU_NODE.PUB.RPY_AERO, self.qos_depth)

        # Describe the physical mounting without relocating acceleration to the COM.
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
        if self.calibration_samples:
            self.get_logger().info(
                f'Calibrating over {self.calibration_samples} samples: '
                'keep the boat stationary and level'
            )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
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
        rotation = rotation_matrix(quaternion_from_degrees(*self.world_rotation_rpy_deg))
        expected = ((1, 0, 0), (0, -1, 0), (0, 0, -1))
        if any(not math.isclose(rotation[i][j], expected[i][j], abs_tol=1e-9)
               for i in range(3) for j in range(3)):
            raise ValueError('The local up-to-down world convention requires 180 degrees of roll')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    def _publish_static_frames(self):
        transforms = []
        # The processed frames share the IMU position; their axes follow the boat.
        offsets = (
            (self.frame_base, self.frame_imu, self.tf_offset),
            (self.frame_base, self.frame_robotic, [*self.tf_offset[:3], 0.0, 0.0, 0.0]),
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
    def publish_attitude(self, msg):
        if (msg.header.frame_id != self.frame_robotic
                or msg.linear_acceleration_covariance[0] == -1
                or msg.angular_velocity_covariance[0] == -1):
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

        angles = RollPitchYaw()
        angles.header = copy.deepcopy(output.header)
        angles.roll_deg = math.degrees(self.filter.roll)
        angles.pitch_deg = math.degrees(self.filter.pitch)
        angles.yaw_deg = math.degrees(self.filter.yaw)

        self.imu_pub.publish(output)
        self.rpy_pub.publish(angles)

    # Complete only the world-reference conversion after the aero transformer.
    def publish_aero(self, msg):
        if msg.header.frame_id != self.frame_aero or msg.orientation_covariance[0] == -1:
            return
        q = msg.orientation
        quaternion = (q.x, q.y, q.z, q.w)
        norm = math.hypot(*quaternion)
        if not math.isfinite(norm) or norm == 0:
            return
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.aero_last_stamp is not None and stamp == self.aero_last_stamp:
            return
        if self.aero_last_stamp is not None and stamp < self.aero_last_stamp:
            self.aero_last_yaw = None
        # Body vectors and their covariance were already transformed by the ROS node.
        # Only orientation and its world-referenced covariance need this left product.
        transformed = multiply(self.world_quaternion, tuple(v / norm for v in quaternion))
        output = copy.deepcopy(msg)
        output.orientation.x, output.orientation.y, output.orientation.z, output.orientation.w = transformed
        output.orientation_covariance = rotate_covariance(self.world_rotation, msg.orientation_covariance)

        rotation = rotation_matrix(transformed)
        roll = math.atan2(rotation[2][1], rotation[2][2])
        pitch = math.asin(max(-1.0, min(1.0, -rotation[2][0])))
        yaw = math.atan2(rotation[1][0], rotation[0][0])
        if self.aero_last_yaw is None:
            self.aero_continuous_yaw = yaw
        else:
            self.aero_continuous_yaw += math.remainder(yaw - self.aero_last_yaw, 2 * math.pi)
        self.aero_last_yaw, self.aero_last_stamp = yaw, stamp
        angles = RollPitchYaw()
        angles.header = copy.deepcopy(msg.header)
        angles.roll_deg = math.degrees(roll)
        angles.pitch_deg = math.degrees(pitch)
        angles.yaw_deg = math.degrees(self.aero_continuous_yaw)
        self.aero_imu_pub.publish(output)
        self.aero_rpy_pub.publish(angles)


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
