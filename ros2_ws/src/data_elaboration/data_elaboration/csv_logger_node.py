"""Archive raw and processed ROS measurements without accessing hardware."""

import csv
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from geometry_msgs.msg import Vector3Stamped
from sensor_msgs.msg import Imu, Range
from sail_msgs.msg import GpsData
from std_msgs.msg import Bool, Float64

from sensors.generated.ros_endpoints import Topics as SensorTopics
from sensors.utils.configuration import depth, parameter
from .generated.ros_endpoints import Topics


class CsvLoggerNode(Node):
    def __init__(self):
        super().__init__('csv_logger_node')
        enabled = parameter(self, 'enabled', Parameter.Type.BOOL)
        directory = parameter(self, 'directory', Parameter.Type.STRING)
        qos = depth(self)
        self.files = []
        self.subscriptions_ = []
        if not enabled:
            return
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        directory = Path(directory).expanduser() / run
        directory.mkdir(parents=True, exist_ok=False)
        imu_fields = ('linear_acceleration.x', 'linear_acceleration.y',
                      'linear_acceleration.z', 'angular_velocity.x',
                      'angular_velocity.y', 'angular_velocity.z',
                      'orientation.x', 'orientation.y', 'orientation.z', 'orientation.w',
                      'orientation_covariance')
        gps_fields = ('latitude_deg', 'longitude_deg', 'altitude_msl_m',
                      'ground_speed_mps', 'course_deg', 'position_dop',
                      'horizontal_accuracy_m', 'vertical_accuracy_m',
                      'satellites_used', 'fix_type', 'fix_valid')
        streams = (
            ('ultrasonic_left', Range, SensorTopics.ULTRASONIC_LEFT_NODE.PUB.RANGE, ('range',)),
            ('ultrasonic_right', Range, SensorTopics.ULTRASONIC_RIGHT_NODE.PUB.RANGE, ('range',)),
            ('ultrasonic_mean', Range, Topics.ULTRASONIC_FILTER_NODE.PUB.MEAN, ('range',)),
            ('gps_raw', GpsData, SensorTopics.GPS_NODE.PUB.GPS_RAW, gps_fields),
            ('compass_raw', Vector3Stamped, SensorTopics.I2C_SENSORS_NODE.PUB.COMPASS_RAW,
             ('vector.x', 'vector.y', 'vector.z')),
            ('imu_raw', Imu, SensorTopics.I2C_SENSORS_NODE.PUB.IMU_RAW, imu_fields),
            ('imu_processed', Imu, Topics.IMU_NODE.PUB.IMU, imu_fields),
            ('heading_deg', Float64, Topics.HEADING_NODE.PUB.HEADING_DEG, ('data',)),
            ('battery_low', Bool, SensorTopics.BATTERY_NODE.PUB.BATTERY_LOW, ('data',)),
        )
        try:
            for name, message, topic, fields in streams:
                file = (directory / f'{name}.csv').open('w', newline='', encoding='utf-8')
                self.files.append(file)
                writer = csv.writer(file)
                writer.writerow(('receipt_ros_ns', 'sample_ros_ns', 'frame_id', *fields))
                file.flush()
                self.subscriptions_.append(self.create_subscription(
                    message, topic,
                    lambda msg, writer=writer, file=file, fields=fields:
                        self.write(msg, writer, file, fields), qos))
        except Exception:
            for file in self.files:
                file.close()
            raise

    def write(self, msg, writer, file, fields):
        receipt = self.get_clock().now().nanoseconds
        header = getattr(msg, 'header', None)
        stamp = '' if header is None else header.stamp.sec * 10**9 + header.stamp.nanosec
        values = []
        for field in fields:
            value = msg
            for part in field.split('.'):
                value = getattr(value, part)
            values.append(value)
        try:
            writer.writerow((receipt, stamp, '' if header is None else header.frame_id, *values))
            file.flush()
        except OSError as error:
            self.get_logger().error(f'CSV write failed: {error}')

    def destroy_node(self):
        for file in self.files:
            file.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CsvLoggerNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
