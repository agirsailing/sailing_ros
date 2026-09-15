"""Publish the digital low-battery signal; system policy lives elsewhere."""

import lgpio
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

from sensors.generated.ros_endpoints import Topics


class BatteryNode(Node):
    def __init__(self):
        super().__init__('battery_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.gpio_chip = self.declare_parameter('gpio_chip', Parameter.Type.INTEGER).value
        self.gpio_line = self.declare_parameter('gpio_line', Parameter.Type.INTEGER).value
        self.active_level = self.declare_parameter('active_level', Parameter.Type.INTEGER).value
        self.pull = self.declare_parameter('pull', Parameter.Type.STRING).value
        self.rate_hz = self.declare_parameter('rate_hz', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration before accessing GPIO.
        self._validate_parameters()

        # 3. Low-battery state publisher.
        self.battery_pub = self.create_publisher(
            Bool,
            Topics.BATTERY_NODE.PUB.BATTERY_LOW,
            self.qos_depth
        )

        # 4. Select the input pull resistor and open the GPIO chip.
        if self.pull == 'up':
            self.pull_flags = lgpio.SET_PULL_UP
        elif self.pull == 'down':
            self.pull_flags = lgpio.SET_PULL_DOWN
        else:
            self.pull_flags = lgpio.SET_PULL_NONE

        self.chip = lgpio.gpiochip_open(self.gpio_chip)
        try:
            lgpio.gpio_claim_input(self.chip, self.gpio_line, self.pull_flags)

            # 5. Timer for reading and publishing the digital battery signal.
            self.battery_timer = self.create_timer(
                1.0 / self.rate_hz,
                self.publish_battery
            )
        except Exception:
            lgpio.gpiochip_close(self.chip)
            raise

        self.get_logger().info(
            f'Battery node initialized on GPIO chip {self.gpio_chip}, '
            f'line {self.gpio_line}, reading at {self.rate_hz} Hz'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Reject missing YAML values before accessing hardware.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if self.active_level not in (0, 1):
            raise ValueError('active_level must be 0 or 1')
        if self.pull not in ('up', 'down', 'none'):
            raise ValueError('pull must be up, down or none')
        if self.rate_hz <= 0:
            raise ValueError('rate_hz must be positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    # -----------------------
    #   Read and publish battery state
    # -----------------------
    def publish_battery(self):
        try:
            level = lgpio.gpio_read(self.chip, self.gpio_line)
            if level not in (0, 1):
                raise OSError(f'Invalid GPIO level: {level}')
        except Exception as error:
            self.get_logger().error(f'Battery GPIO read failed: {error}')
            return

        msg = Bool()
        msg.data = level == self.active_level

        self.battery_pub.publish(msg)

    # -----------------------
    #   Release the GPIO chip
    # -----------------------
    def destroy_node(self):
        lgpio.gpiochip_close(self.chip)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BatteryNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
