"""React to battery state separately from GPIO acquisition."""

import subprocess
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

from sensors.generated.ros_endpoints import Topics as SensorTopics
from sensors.utils.configuration import depth, parameter


class BatteryMonitorNode(Node):
    def __init__(self):
        super().__init__('battery_monitor_node')
        self.enabled = parameter(self, 'shutdown_enabled', Parameter.Type.BOOL)
        self.required = parameter(self, 'low_samples_required', Parameter.Type.INTEGER)
        self.command = parameter(self, 'shutdown_command', Parameter.Type.STRING_ARRAY)
        if self.required < 1 or not self.command:
            raise ValueError('Configure a positive sample count and shutdown command')
        self.low_samples = 0
        self.triggered = False
        self.subscription = self.create_subscription(
            Bool, SensorTopics.BATTERY_NODE.PUB.BATTERY_LOW, self.receive, depth(self))

    def receive(self, msg):
        self.low_samples = self.low_samples + 1 if msg.data else 0
        if self.triggered or self.low_samples < self.required:
            return
        self.triggered = True
        if not self.enabled:
            self.get_logger().warning('Battery low; shutdown is disabled in this mode')
            return
        self.get_logger().fatal('Battery low; requesting system shutdown')
        try:
            # Do not kill ROS first: that could terminate this callback before
            # the shutdown request is issued. Never invoke a shell.
            result = subprocess.run(self.command, check=False)
            if result.returncode:
                self.get_logger().error(f'Shutdown returned {result.returncode}')
        except OSError as error:
            self.get_logger().error(f'Failed to request shutdown: {error}')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BatteryMonitorNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
