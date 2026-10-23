"""Publish battery data and request shutdown after a confirmed low-battery alarm."""

import math
import subprocess
import time

import lgpio
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sail_msgs.msg import BatteryData
from sail_common.freshness import is_fresh

from sensors.drivers.battery_driver import BatteryDriver
from sensors.generated.ros_endpoints import Topics


class BatteryNode(Node):
    def __init__(self):
        super().__init__('battery_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.gpio_chip = self.declare_parameter('gpio_chip', Parameter.Type.INTEGER).value
        self.gpio_line = self.declare_parameter('gpio_line', Parameter.Type.INTEGER).value
        self.link_gpio_line = self.declare_parameter('link_gpio_line', Parameter.Type.INTEGER).value
        self.active_level = self.declare_parameter('active_level', Parameter.Type.INTEGER).value
        self.pull = self.declare_parameter('pull', Parameter.Type.STRING).value
        self.read_rate_hz = self.declare_parameter('read_rate_hz', Parameter.Type.DOUBLE).value
        self.publish_rate_hz = self.declare_parameter('publish_rate_hz', Parameter.Type.DOUBLE).value
        self.max_sample_age_s = self.declare_parameter('max_sample_age_s', Parameter.Type.DOUBLE).value
        self.voltage_max_age_s = self.declare_parameter('voltage_max_age_s', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value
        self.shutdown_enabled = self.declare_parameter('shutdown_enabled', Parameter.Type.BOOL).value
        self.low_samples_required = self.declare_parameter('low_samples_required', Parameter.Type.INTEGER).value
        self.shutdown_command = self.declare_parameter('shutdown_command', Parameter.Type.STRING_ARRAY).value

        # 2. Validate configuration before accessing GPIO.
        self._validate_parameters()
        self.low_samples = 0
        self.shutdown_requested = False
        self._sample = None

        # 3. One hardware snapshot for both voltage and the raw low alarm.
        self.battery_pub = self.create_publisher(
            BatteryData,
            Topics.BATTERY_NODE.PUB.BATTERY_DATA,
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
        self.link = None
        try:
            lgpio.gpio_claim_input(self.chip, self.gpio_line, self.pull_flags)
            self.link = BatteryDriver(self.chip, self.link_gpio_line)

            # 5. GPIO polling and shutdown checks are independent of publication.
            # Both timers use the default mutually exclusive callback group.
            self.read_timer = self.create_timer(
                1.0 / self.read_rate_hz,
                self.read_battery
            )
            self.battery_timer = self.create_timer(
                1.0 / self.publish_rate_hz,
                self.publish_battery
            )
        except Exception:
            if self.link is not None:
                self.link.close()
            lgpio.gpiochip_close(self.chip)
            raise

        self.get_logger().info(
            f'Battery node initialized on GPIO chip {self.gpio_chip}, '
            f'line {self.gpio_line}, voltage link on line {self.link_gpio_line}, '
            f'reading the alarm at {self.read_rate_hz} Hz, '
            f'publishing at {self.publish_rate_hz} Hz'
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
        for name in ('read_rate_hz', 'publish_rate_hz',
                     'max_sample_age_s', 'voltage_max_age_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if self.low_samples_required < 1:
            raise ValueError('low_samples_required must be positive')
        if not self.shutdown_command:
            raise ValueError('shutdown_command must not be empty')

    # -----------------------
    #   Read the GPIO alarm and check shutdown once per successful read
    # -----------------------
    def read_battery(self):
        try:
            level = lgpio.gpio_read(self.chip, self.gpio_line)
            if level not in (0, 1):
                raise OSError(f'Invalid GPIO level: {level}')
        except Exception as error:
            self._sample = None
            self.get_logger().error(f'Battery GPIO read failed: {error}')
            return

        stamp = self.get_clock().now().to_msg()
        low = level == self.active_level
        # The voltage driver replaces its immutable (volts, decode-time) tuple.
        # Its timestamp is independent of this GPIO read's ROS timestamp.
        self._sample = (stamp, time.monotonic(), low, self.link.latest)
        self._check_shutdown(low)

    def publish_battery(self):
        sample = self._sample
        if sample is None:
            return
        stamp, received_at, low, latest = sample
        now = time.monotonic()
        # Check each clock domain separately, including when ROS time is paused.
        if (not is_fresh(stamp, self.get_clock().now(), self.max_sample_age_s)
                or not is_fresh(received_at, now, self.max_sample_age_s)):
            return

        msg = BatteryData()
        msg.header.stamp = stamp
        # Leave frame_id empty: these scalars do not refer to spatial axes.
        msg.low = low
        # Recheck voltage age on every publication; repeated GPIO reads or
        # publications must not make an old voltage look freshly received.
        if latest is None or not is_fresh(latest[1], now, self.voltage_max_age_s):
            msg.voltage_v = math.nan
        else:
            msg.voltage_v = latest[0]

        self.battery_pub.publish(msg)

    def _check_shutdown(self, low):
        # Keep publishing the raw alarm; confirmation only controls shutdown.
        if low:
            self.low_samples = min(self.low_samples + 1, self.low_samples_required)
        else:
            self.low_samples = 0

        if self.low_samples < self.low_samples_required or self.shutdown_requested:
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

    # -----------------------
    #   Release the GPIO chip
    # -----------------------
    def destroy_node(self):
        self.link.close()
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
