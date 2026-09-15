"""Combine independent GPS and compass topics without hardware access."""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from geometry_msgs.msg import Vector3Stamped
from sail_msgs.msg import GpsData
from std_msgs.msg import Float64, String

from sensors.generated.ros_endpoints import Topics as SensorTopics
from sensors.utils.configuration import depth, parameter, positive
from .generated.ros_endpoints import Topics
from .processing.heading import choose_heading


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


class HeadingNode(Node):
    def __init__(self):
        super().__init__('heading_node')
        self.threshold = positive(self, 'gps_speed_threshold_mps')
        self.max_age = positive(self, 'max_input_age_s')
        self.options = [parameter(self, key, Parameter.Type.DOUBLE) for key in (
            'compass_x_sign', 'compass_y_sign', 'compass_x_bias',
            'compass_y_bias', 'heading_offset_deg')]
        if any(sign not in (-1.0, 1.0) for sign in self.options[:2]):
            raise ValueError('Compass axis signs must be -1.0 or 1.0')
        rate = positive(self, 'rate_hz')
        qos = depth(self)
        self.gps = self.compass = None
        self.last_now = None
        self.publisher = self.create_publisher(
            Float64, Topics.HEADING_NODE.PUB.HEADING_DEG, qos)
        self.summary = self.create_publisher(
            String, Topics.HEADING_NODE.PUB.GPS_SUMMARY, qos)
        self.gps_sub = self.create_subscription(
            GpsData, SensorTopics.GPS_NODE.PUB.GPS_RAW, self.on_gps, qos)
        self.compass_sub = self.create_subscription(
            Vector3Stamped, SensorTopics.I2C_SENSORS_NODE.PUB.COMPASS_RAW,
            self.on_compass, qos)
        self.timer = self.create_timer(1.0 / rate, self.publish_heading)

    def on_gps(self, msg):
        self.gps = msg

    def on_compass(self, msg):
        self.compass = msg

    def publish_heading(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        if self.last_now is not None and now < self.last_now:
            self.gps = self.compass = None
        self.last_now = now
        gps = None if self.gps is None else (
            seconds(self.gps.header.stamp), self.gps.fix_valid,
            self.gps.ground_speed_mps, self.gps.course_deg)
        compass = None if self.compass is None else (
            seconds(self.compass.header.stamp), self.compass.vector.x,
            self.compass.vector.y)
        heading = choose_heading(gps, compass, now, self.max_age,
                                 self.threshold, *self.options)
        self.publisher.publish(Float64(data=heading))
        # Keep the previous human-readable /gps interface for existing clients.
        text = String()
        if gps is None or not gps[1] or not 0 <= now - gps[0] <= self.max_age:
            text.data = 'No GPS signal'
        else:
            text.data = (
                f'lat={self.gps.latitude_deg:.7f}, lon={self.gps.longitude_deg:.7f}, '
                f'speed={self.gps.ground_speed_mps * (3600.0 / 1852.0):.2f}kn, '
                f'heading={heading:.1f}deg')
        self.summary.publish(text)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = HeadingNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
