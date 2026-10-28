# /ros2_ws/src/sensors/sensors/i2c_sensors_node.py
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from geometry_msgs.msg import Vector3Stamped
from smbus2 import SMBus
from sail_common.freshness import is_fresh

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
        self.compass_read_rate_hz = self.declare_parameter('compass.read_rate_hz', Parameter.Type.DOUBLE).value
        self.compass_publish_rate_hz = self.declare_parameter('compass.publish_rate_hz', Parameter.Type.DOUBLE).value
        self.compass_max_sample_age_s = self.declare_parameter('compass.max_sample_age_s', Parameter.Type.DOUBLE).value
        self.compass_reset_value = self.declare_parameter('compass.reset_value', Parameter.Type.INTEGER).value
        self.compass_measurement_value = self.declare_parameter('compass.measurement_value', Parameter.Type.INTEGER).value
        self.compass_reset_delay_s = self.declare_parameter('compass.reset_delay_s', Parameter.Type.DOUBLE).value
        self.compass_conversion_delay_s = self.declare_parameter('compass.conversion_delay_s', Parameter.Type.DOUBLE).value

        # 2. Validate configuration before opening the I2C bus.
        self._validate_parameters()

        # 3. Internal state: each sensor has its own driver and retry deadline.
        self.compass_driver = None
        self.compass_retry_at = 0.0
        self._stop = threading.Event()
        self._sample_lock = threading.Lock()
        self._samples = {'compass': None}
        self._workers = []
        self.mux = None
        self._bus = None

        if not self.compass_enabled:
            self.get_logger().info('I2C compass acquisition disabled')
            return

        # 4. Open the shared bus and multiplexer.
        # Drivers hold the mux lock across channel selection, reading and
        # deselection. No other process may manually operate this multiplexer.
        try:
            self._bus = SMBus(self.bus_number)
            self.mux = I2CMultiplexer(
                self._bus, self.mux_address, self.mux_channel_count
            )
            # 5. Sensor publishers.
            if self.compass_enabled:
                self.compass_pub = self.create_publisher(
                    Vector3Stamped,
                    Topics.I2C_SENSORS_NODE.PUB.COMPASS_DATA,
                    self.qos_depth
                )

            # 6. ROS timers publish snapshots only. Dedicated workers perform
            # polling; the existing mux lock serializes complete bus transactions.
            # Driver initialization/retries happen in each sensor's own worker.
            if self.compass_enabled:
                self.compass_timer = self.create_timer(
                    1.0 / self.compass_publish_rate_hz,
                    self.publish_compass
                )
                self._workers.append(threading.Thread(
                    target=self._read_loop,
                    args=(self.read_compass, self.compass_read_rate_hz),
                    name='i2c_compass_reader', daemon=True
                ))
            else:
                self.get_logger().info('Compass acquisition disabled')
            for worker in self._workers:
                worker.start()
        except Exception:
            self.destroy_node()
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
        for name, value in (
            ('retry_interval_s', self.retry_interval_s),
            ('compass.read_rate_hz', self.compass_read_rate_hz),
            ('compass.publish_rate_hz', self.compass_publish_rate_hz),
            ('compass.max_sample_age_s', self.compass_max_sample_age_s),
            ('compass.reset_delay_s', self.compass_reset_delay_s),
            ('compass.conversion_delay_s', self.compass_conversion_delay_s),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not 0 <= self.compass_channel < self.mux_channel_count:
            raise ValueError('Invalid compass.channel')

    # -----------------------
    #   Poll independently of publication; never queue catch-up reads
    # -----------------------
    def _read_loop(self, read, rate_hz):
        period = 1.0 / rate_hz
        while not self._stop.is_set():
            started = time.monotonic()
            read()
            self._stop.wait(max(0.0, period - (time.monotonic() - started)))

    def _store_sample(self, name, message):
        # Each completed read is timestamped on the host, not by the device.
        sample = (message, time.monotonic()) if message is not None else None
        with self._sample_lock:
            self._samples[name] = sample

    # -----------------------
    #   Read compass measurements using the unchanged driver/conversion delay
    # -----------------------
    def read_compass(self):
        if time.monotonic() < self.compass_retry_at:
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
            self._store_sample('compass', None)
            self.compass_retry_at = time.monotonic() + self.retry_interval_s
            return

        msg = Vector3Stamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.compass_frame_id

        # Publish raw signed sensor counts, without calculating a heading.
        msg.vector.x = float(x)
        msg.vector.y = float(y)
        msg.vector.z = float(z)

        self._store_sample('compass', msg)

    def _publish_latest(self, name, publisher, max_age_s):
        with self._sample_lock:
            sample = self._samples[name]
        if sample is None:
            return
        msg, received_at = sample
        # Separate clock domains: source ROS time and elapsed monotonic time.
        # Pausing ROS time must not keep a disconnected sensor fresh forever.
        if (not is_fresh(msg.header.stamp, self.get_clock().now(), max_age_s)
                or not is_fresh(received_at, time.monotonic(), max_age_s)):
            return
        # Never mutate a cached message or refresh its stamp on republication.
        publisher.publish(msg)

    def publish_compass(self):
        self._publish_latest('compass', self.compass_pub, self.compass_max_sample_age_s)

    # -----------------------
    #   Release the multiplexer and I2C bus
    # -----------------------
    def destroy_node(self):
        self._stop.set()
        # Let in-flight driver transactions finish before releasing the bus.
        for worker in self._workers:
            if worker.is_alive():
                worker.join()
        if self.mux is not None:
            self.mux.close()
            self.mux = None
            self._bus = None
        elif self._bus is not None:
            self._bus.close()
            self._bus = None
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
