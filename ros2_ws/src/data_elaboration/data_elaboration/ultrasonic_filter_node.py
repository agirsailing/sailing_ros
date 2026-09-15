"""Pair ultrasonic measurements by acquisition timestamp and average them."""

import copy
import math
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Range

from sensors.generated.ros_endpoints import Topics as SensorTopics
from sensors.utils.configuration import depth, parameter, positive
from .generated.ros_endpoints import Topics


class UltrasonicFilterNode(Node):
    def __init__(self):
        super().__init__('ultrasonic_filter_node')
        self.max_dt = positive(self, 'max_pair_dt_s')
        self.frame_id = parameter(self, 'frame_id', Parameter.Type.STRING)
        qos = depth(self)
        self.left = self.right = None
        self.publisher = self.create_publisher(
            Range, Topics.ULTRASONIC_FILTER_NODE.PUB.MEAN, qos)
        self.sub_left = self.create_subscription(
            Range, SensorTopics.ULTRASONIC_LEFT_NODE.PUB.RANGE,
            lambda msg: self.receive('left', msg), qos)
        self.sub_right = self.create_subscription(
            Range, SensorTopics.ULTRASONIC_RIGHT_NODE.PUB.RANGE,
            lambda msg: self.receive('right', msg), qos)

    def receive(self, side, msg):
        if not math.isfinite(msg.range) or not msg.min_range <= msg.range <= msg.max_range:
            return
        setattr(self, side, msg)
        if self.left is None or self.right is None:
            return
        left_ns = self.left.header.stamp.sec * 10**9 + self.left.header.stamp.nanosec
        right_ns = self.right.header.stamp.sec * 10**9 + self.right.header.stamp.nanosec
        if abs(left_ns - right_ns) > self.max_dt * 1e9:
            # Discard the older sample so it cannot be reused.
            if left_ns < right_ns:
                self.left = None
            else:
                self.right = None
            return
        output = copy.deepcopy(self.left if left_ns >= right_ns else self.right)
        output.header.frame_id = self.frame_id
        output.range = (self.left.range + self.right.range) / 2.0
        self.publisher.publish(output)
        self.left = self.right = None


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UltrasonicFilterNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
