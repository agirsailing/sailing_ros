"""Publish the receiver solution without compass access or heading fusion."""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from serial import Serial
from pyubx2 import UBXReader
from sail_msgs.msg import GpsData
from sail_common.freshness import is_fresh

from sensors.drivers.gps_driver import InterruptibleSerialStream, nav_pvt_values
from sensors.generated.ros_endpoints import Topics


class GPSNode(Node):
    def __init__(self):
        super().__init__('gps_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.port = self.declare_parameter('port', Parameter.Type.STRING).value
        self.baudrate = self.declare_parameter('baudrate', Parameter.Type.INTEGER).value
        self.timeout_s = self.declare_parameter('timeout_s', Parameter.Type.DOUBLE).value
        self.read_rate_hz = self.declare_parameter('read_rate_hz', Parameter.Type.DOUBLE).value
        self.publish_rate_hz = self.declare_parameter('publish_rate_hz', Parameter.Type.DOUBLE).value
        self.max_sample_age_s = self.declare_parameter('max_sample_age_s', Parameter.Type.DOUBLE).value
        self.frame_id = self.declare_parameter('frame_id', Parameter.Type.STRING).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration before opening the serial port.
        self._validate_parameters()

        # 3. GPS data publisher.
        self.gps_pub = self.create_publisher(
            GpsData,
            Topics.GPS_NODE.PUB.GPS_DATA,
            self.qos_depth
        )

        self.stream = None
        self._reader_thread = None
        self._stop = threading.Event()
        self._sample_lock = threading.Lock()
        self._latest_sample = None
        # Read outside the ROS executor. Partial packets survive idle timeouts.
        try:
            self.stream = Serial(self.port, self.baudrate, timeout=self.timeout_s)
            self.reader = UBXReader(InterruptibleSerialStream(self.stream, self._stop))
            self.gps_timer = self.create_timer(
                1.0 / self.publish_rate_hz,
                self.publish_gps
            )
            self._reader_thread = threading.Thread(
                target=self._read_loop, name='gps_reader', daemon=True
            )
            self._reader_thread.start()
        except Exception:
            self.destroy_node()
            raise

        read_mode = 'on data arrival' if self.read_rate_hz == 0 else f'at {self.read_rate_hz} Hz'
        self.get_logger().info(
            f'GPS node initialized on {self.port}, reading {read_mode}, '
            f'publishing at {self.publish_rate_hz} Hz'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Reject missing YAML values before accessing hardware.
        self.get_parameters(self.list_parameters([], depth=0).names)

        for name in ('timeout_s', 'publish_rate_hz', 'max_sample_age_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not math.isfinite(self.read_rate_hz) or self.read_rate_hz < 0:
            raise ValueError('read_rate_hz must be zero (on arrival) or finite and positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    # -----------------------
    #   Continuously decode; retain the latest NAV-PVT, including invalid fixes
    # -----------------------
    def _read_loop(self):
        period = 1.0 / self.read_rate_hz if self.read_rate_hz > 0 else 0.0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                if period == 0:
                    self._read_packet()
                else:
                    # Drain the backlog on each poll, not just one packet/tick.
                    while not self._stop.is_set() and self.stream.in_waiting:
                        self._read_packet()
            except Exception as error:
                with self._sample_lock:
                    self._latest_sample = None
                if not self._stop.is_set():
                    self.get_logger().warning(
                        f'GPS read failed: {error}', throttle_duration_sec=5.0
                    )
                self._stop.wait(self.timeout_s)
            self._stop.wait(max(0.0, period - (time.monotonic() - started)))

    def _read_packet(self):
        _, packet = self.reader.read()
        if self._stop.is_set() or packet is None or packet.identity != 'NAV-PVT':
            return
        # Host decoding time, not receiver measurement time (nor UTC from GPS).
        stamp = self.get_clock().now().to_msg()
        received_at = time.monotonic()
        try:
            values = nav_pvt_values(packet)
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            with self._sample_lock:
                self._latest_sample = None
            self.get_logger().warning(
                f'GPS NAV-PVT rejected: {error}', throttle_duration_sec=5.0
            )
            return
        with self._sample_lock:
            self._latest_sample = (values, stamp, received_at)

    def publish_gps(self):
        with self._sample_lock:
            sample = self._latest_sample
        if sample is None:
            return
        values, stamp, received_at = sample
        if (not is_fresh(stamp, self.get_clock().now(), self.max_sample_age_s)
                or not is_fresh(received_at, time.monotonic(), self.max_sample_age_s)):
            return

        msg = GpsData()
        # Cached publications preserve acquisition time and receiver fix status.
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id

        # The driver decodes the receiver fields and converts physical units.
        msg.latitude_deg = values['latitude_deg']
        msg.longitude_deg = values['longitude_deg']
        msg.altitude_msl_m = values['altitude_msl_m']
        msg.ground_speed_mps = values['ground_speed_mps']
        msg.course_deg = values['course_deg']
        msg.position_dop = values['position_dop']
        msg.horizontal_accuracy_m = values['horizontal_accuracy_m']
        msg.vertical_accuracy_m = values['vertical_accuracy_m']
        msg.satellites_used = values['satellites_used']
        msg.fix_type = values['fix_type']
        msg.fix_valid = values['fix_valid']

        self.gps_pub.publish(msg)

    # -----------------------
    #   Release the serial connection
    # -----------------------
    def destroy_node(self):
        self._stop.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join()
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = GPSNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
