"""Publish the digital low-battery signal; system policy lives elsewhere."""

import lgpio
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

from .generated.ros_endpoints import Topics
from .utils.configuration import depth, parameter, positive


class BatteryNode(Node):
    def __init__(self):
        super().__init__('battery_node')
        chip = parameter(self, 'gpio_chip', Parameter.Type.INTEGER)
        self.line = parameter(self, 'gpio_line', Parameter.Type.INTEGER)
        self.active = parameter(self, 'active_level', Parameter.Type.INTEGER)
        pull = parameter(self, 'pull', Parameter.Type.STRING)
        flags = {'up': lgpio.SET_PULL_UP, 'down': lgpio.SET_PULL_DOWN,
                 'none': lgpio.SET_PULL_NONE}[pull]
        if self.active not in (0, 1):
            raise ValueError('active_level must be 0 or 1')
        rate = positive(self, 'rate_hz')
        self.publisher = self.create_publisher(
            Bool, Topics.BATTERY_NODE.PUB.BATTERY_LOW, depth(self))
        self.chip = lgpio.gpiochip_open(chip)
        try:
            lgpio.gpio_claim_input(self.chip, self.line, flags)
        except Exception:
            lgpio.gpiochip_close(self.chip)
            raise
        self.timer = self.create_timer(1.0 / rate, self.read)

    def read(self):
        try:
            level = lgpio.gpio_read(self.chip, self.line)
            if level not in (0, 1):
                raise OSError(f'Invalid GPIO level: {level}')
        except Exception as error:
            self.get_logger().error(f'Battery GPIO read failed: {error}')
            return
        msg = Bool()
        msg.data = level == self.active
        self.publisher.publish(msg)

    def destroy_node(self):
        lgpio.gpiochip_close(self.chip)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BatteryNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
