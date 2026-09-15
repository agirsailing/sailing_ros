"""Publish the receiver solution without compass access or heading fusion."""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from serial import Serial
from pyubx2 import UBXReader
from sail_msgs.msg import GpsData

from .drivers.gps_driver import nav_pvt_values
from .generated.ros_endpoints import Topics
from .utils.configuration import depth, parameter, positive


class GPSNode(Node):
    def __init__(self):
        super().__init__('gps_node')
        port = parameter(self, 'port', Parameter.Type.STRING)
        baud = parameter(self, 'baudrate', Parameter.Type.INTEGER)
        timeout = positive(self, 'timeout_s')
        rate = positive(self, 'rate_hz')
        self.frame_id = parameter(self, 'frame_id', Parameter.Type.STRING)
        self.publisher = self.create_publisher(
            GpsData, Topics.GPS_NODE.PUB.GPS_RAW, depth(self))
        self.stream = Serial(port, baud, timeout=timeout)
        self.reader = UBXReader(self.stream)
        self.timer = self.create_timer(1.0 / rate, self.read)

    def read(self):
        try:
            _, packet = self.reader.read()
            if packet is None or packet.identity != 'NAV-PVT':
                return
            values = nav_pvt_values(packet)
        except Exception as error:
            self.get_logger().warning(f'GPS read failed: {error}')
            return
        msg = GpsData()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        for field, value in values.items():
            setattr(msg, field, value)
        self.publisher.publish(msg)

    def destroy_node(self):
        self.stream.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = GPSNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
