"""Confirm a low-battery alarm and apply the existing shutdown policy.

The input contains only a digital alarm. Voltage, charge percentage and charging
status cannot be inferred from it.
"""

import subprocess
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

from sensors.generated.ros_endpoints import Topics as SensorTopics
from data_elaboration.generated.ros_endpoints import Topics


class BatteryMonitorNode(Node):
    def __init__(self):
        super().__init__('battery_monitor_node')

        # 1. Declare and read parameters.
        self.shutdown_enabled = self.declare_parameter('shutdown_enabled', Parameter.Type.BOOL).value
        self.low_samples_required = self.declare_parameter('low_samples_required', Parameter.Type.INTEGER).value
        self.shutdown_command = self.declare_parameter('shutdown_command', Parameter.Type.STRING_ARRAY).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration and initialize alarm state.
        self._validate_parameters()
        self.low_samples = 0
        self.shutdown_requested = False

        # 3. Publish the alarm confirmed by the configured consecutive samples.
        self.battery_pub = self.create_publisher(
            Bool,
            Topics.BATTERY_MONITOR_NODE.PUB.BATTERY_LOW,
            self.qos_depth
        )

        # 4. Subscribe to the raw digital battery signal.
        self.battery_sub = self.create_subscription(
            Bool,
            SensorTopics.BATTERY_NODE.PUB.BATTERY_DATA,
            self.publish_battery_state,
            self.qos_depth
        )

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        if self.low_samples_required < 1:
            raise ValueError('low_samples_required must be positive')
        if not self.shutdown_command:
            raise ValueError('shutdown_command must not be empty')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    # -----------------------
    #   Publish the confirmed alarm and apply the shutdown policy
    # -----------------------
    def publish_battery_state(self, msg):
        if msg.data:
            self.low_samples = min(self.low_samples + 1, self.low_samples_required)
        else:
            self.low_samples = 0

        state = Bool()
        state.data = self.low_samples >= self.low_samples_required
        self.battery_pub.publish(state)

        if not state.data or self.shutdown_requested:
            return
        self.shutdown_requested = True
        if not self.shutdown_enabled:
            self.get_logger().warning('Battery low; shutdown is disabled')
            return
        self._request_shutdown()

    def _request_shutdown(self):
        self.get_logger().fatal('Battery low; requesting system shutdown')
        try:
            result = subprocess.run(self.shutdown_command, check=False)
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
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
