# /ros2_ws/src/sensors/sensors/i2c_sensors_node.py
"""Acquire the magnetometer (compass) on the shared I2C bus and multiplexer.

The BNO085 IMU moved to its own UART node: sensors/imu_sensor_node.py.
"""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from geometry_msgs.msg import Vector3Stamped
from smbus2 import SMBus

from sensors.drivers.i2c_mux import I2CMultiplexer
from sensors.drivers.compass_driver import CompassDriver
from sensors.generated.ros_endpoints import Topics


class I2CSensorsNode(Node):
    def __init__(self):
        super().__init__('i2c_sensors_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        # Shared bus configuration.
        self.bus_number = self.declare_parameter('bus', Parameter.Type.INTEGER).value
        self.mux_address = self.declare_parameter('mux_address', Parameter.Type.INTEGER).value
        self.mux_channel_count = self.declare_parameter('mux_channel_count', Parameter.Type.INTEGER).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value
        self.retry_interval_s = self.declare_parameter('retry_interval_s', Parameter.Type.DOUBLE).value

        # Compass configuration.
        self.compass_enabled = self.declare_parameter('compass.enabled', Parameter.Type.BOOL).value
        self.compass_channel = self.declare_parameter('compass.channel', Parameter.Type.INTEGER).value
        self.compass_address = self.declare_parameter('compass.address', Parameter.Type.INTEGER).value
        self.compass_frame_id = self.declare_parameter('compass.frame_id', Parameter.Type.STRING).value
        self.compass_rate_hz = self.declare_parameter('compass.rate_hz', Parameter.Type.DOUBLE).value
        self.compass_reset_value = self.declare_parameter('compass.reset_value', Parameter.Type.INTEGER).value
        self.compass_measurement_value = self.declare_parameter('compass.measurement_value', Parameter.Type.INTEGER).value
        self.compass_reset_delay_s = self.declare_parameter('compass.reset_delay_s', Parameter.Type.DOUBLE).value
        self.compass_conversion_delay_s = self.declare_parameter('compass.conversion_delay_s', Parameter.Type.DOUBLE).value

        # 2. Validate configuration before opening the I2C bus.
        self._validate_parameters()

        # 3. Internal state: the driver is (re)built on the timer with a retry deadline.
        self.compass_driver = None
        self.compass_retry_at_ns = 0

        # 4. Open the shared bus and multiplexer.
        # Drivers hold the mux lock across channel selection, reading and
        # deselection. No other process may manually operate this multiplexer.
        self.mux = I2CMultiplexer(
            SMBus(self.bus_number),
            self.mux_address,
            self.mux_channel_count
        )

        try:
            # 5. Publisher and reading timer. Driver initialization happens on
            # the first callback so a missing sensor can be retried.
            if self.compass_enabled:
                self.compass_pub = self.create_publisher(
                    Vector3Stamped,
                    Topics.I2C_SENSORS_NODE.PUB.COMPASS_DATA,
                    self.qos_depth
                )
                self.compass_timer = self.create_timer(
                    1.0 / self.compass_rate_hz,
                    self.publish_compass
                )
            else:
                self.get_logger().info('Compass acquisition disabled')
        except Exception:
            self.mux.close()
            raise

        self.get_logger().info(
            f'I2C sensors node initialized on bus {self.bus_number}, '
            f'multiplexer address {self.mux_address:#04x}'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Typed declarations can return None if a YAML entry is missing.
        # Reading all declared parameters raises a clear ROS error in that case.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if self.retry_interval_s <= 0:
            raise ValueError('retry_interval_s must be positive')
        if self.compass_rate_hz <= 0:
            raise ValueError('compass.rate_hz must be positive')
        if self.compass_reset_delay_s <= 0:
            raise ValueError('compass.reset_delay_s must be positive')
        if self.compass_conversion_delay_s <= 0:
            raise ValueError('compass.conversion_delay_s must be positive')
        if not 0 <= self.compass_channel < self.mux_channel_count:
            raise ValueError('Invalid compass.channel')

    # -----------------------
    #   Read and publish compass measurements
    # -----------------------
    def publish_compass(self):
        now_ns = self.get_clock().now().nanoseconds
        if now_ns < self.compass_retry_at_ns:
            return

        try:
            if self.compass_driver is None:
                self.compass_driver = CompassDriver(
                    self.mux,
                    self.compass_channel,
                    self.compass_address,
                    self.compass_reset_value,
                    self.compass_measurement_value,
                    self.compass_reset_delay_s,
                    self.compass_conversion_delay_s
                )

            x, y, z = self.compass_driver.read()
        except Exception as error:
            self.get_logger().error(f'Compass acquisition failed: {error}')
            self.compass_driver = None
            self.compass_retry_at_ns = now_ns + int(self.retry_interval_s * 1e9)
            return

        msg = Vector3Stamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.compass_frame_id

        # Publish raw signed sensor counts, without calculating a heading.
        msg.vector.x = float(x)
        msg.vector.y = float(y)
        msg.vector.z = float(z)

        self.compass_pub.publish(msg)

    # -----------------------
    #   Release the multiplexer and I2C bus
    # -----------------------
    def destroy_node(self):
        self.mux.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = I2CSensorsNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()