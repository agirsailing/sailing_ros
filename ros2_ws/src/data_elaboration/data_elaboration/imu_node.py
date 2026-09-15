"""Calibrate and estimate orientation from the raw IMU ROS topic."""

import copy
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu

from sensors.generated.ros_endpoints import Topics as SensorTopics
from sensors.utils.configuration import depth, parameter, positive
from .generated.ros_endpoints import Topics
from .processing.imu_filter import ImuFilter


class ImuNode(Node):
    def __init__(self):
        super().__init__('imu_node')
        samples = parameter(self, 'calibration_samples', Parameter.Type.INTEGER)
        gravity = positive(self, 'gravity_mps2')
        alpha = parameter(self, 'complementary_alpha', Parameter.Type.DOUBLE)
        max_dt = positive(self, 'max_sample_dt_s')
        self.filter = ImuFilter(samples, gravity, alpha, max_dt)
        qos = depth(self)
        self.publisher = self.create_publisher(Imu, Topics.IMU_NODE.PUB.IMU, qos)
        self.subscription = self.create_subscription(
            Imu, SensorTopics.I2C_SENSORS_NODE.PUB.IMU_RAW, self.process, qos)
        if samples:
            self.get_logger().info(
                f'Calibrating over {samples} samples: keep IMU stationary and level')

    def process(self, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        a, g = msg.linear_acceleration, msg.angular_velocity
        result = self.filter.update(stamp, (a.x, a.y, a.z), (g.x, g.y, g.z))
        if result is None:
            return
        accel, gyro, quaternion = result
        output = copy.deepcopy(msg)
        output.linear_acceleration.x, output.linear_acceleration.y, output.linear_acceleration.z = accel
        output.angular_velocity.x, output.angular_velocity.y, output.angular_velocity.z = gyro
        output.orientation.x, output.orientation.y, output.orientation.z, output.orientation.w = quaternion
        # Estimate exists; zero covariance denotes unknown uncertainty.
        output.orientation_covariance = [0.0] * 9
        self.publisher.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ImuNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
