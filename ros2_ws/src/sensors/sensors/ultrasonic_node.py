# /ros2_ws/src/sensors/sensors/ultrasonic_node.py
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Range
from sail_common.freshness import is_fresh

from sensors.drivers.ultrasonic_driver import DFRobot_A02_Distance
from sensors.generated.ros_endpoints import Topics


class UltrasonicNode(Node):
    def __init__(self):
        super().__init__('ultrasonic_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.enabled = self.declare_parameter('enabled', Parameter.Type.BOOL).value
        self.endpoint_group = self.declare_parameter('endpoint_group', Parameter.Type.STRING).value
        self.port = self.declare_parameter('port', Parameter.Type.STRING).value
        self.baudrate = self.declare_parameter('baudrate', Parameter.Type.INTEGER).value
        self.timeout_s = self.declare_parameter('timeout_s', Parameter.Type.DOUBLE).value
        self.read_rate_hz = self.declare_parameter('read_rate_hz', Parameter.Type.DOUBLE).value
        self.publish_rate_hz = self.declare_parameter('publish_rate_hz', Parameter.Type.DOUBLE).value
        self.max_sample_age_s = self.declare_parameter('max_sample_age_s', Parameter.Type.DOUBLE).value
        self.frame_id = self.declare_parameter('frame_id', Parameter.Type.STRING).value
        self.min_range_m = self.declare_parameter('min_range_m', Parameter.Type.DOUBLE).value
        self.max_range_m = self.declare_parameter('max_range_m', Parameter.Type.DOUBLE).value
        self.field_of_view_rad = self.declare_parameter('field_of_view_rad', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration and select the generated topic constant.
        self._validate_parameters()

        if self.endpoint_group == 'ULTRASONIC_LEFT_NODE':
            self.range_topic = Topics.ULTRASONIC_LEFT_NODE.PUB.RANGE
        else:
            self.range_topic = Topics.ULTRASONIC_RIGHT_NODE.PUB.RANGE

        # A disabled sensor does not open a serial port or publish messages.
        self.sensor = None
        self._reader = None
        self._stop = threading.Event()
        self._sample_lock = threading.Lock()
        self._latest_sample = None
        if not self.enabled:
            self.get_logger().info(
                f'Ultrasonic sensor disabled: {self.frame_id}'
            )
            return

        # 3. Distance publisher.
        self.range_pub = self.create_publisher(
            Range,
            self.range_topic,
            self.qos_depth
        )

        # Serial waits run outside the ROS executor; publication has its own timer.
        try:
            self.sensor = DFRobot_A02_Distance(
                self.port, self.baudrate, self.timeout_s
            )
            self.sensor.set_dis_range(
                self.min_range_m * 1000, self.max_range_m * 1000
            )
            self.distance_timer = self.create_timer(
                1.0 / self.publish_rate_hz, self.publish_distance
            )
            self._reader = threading.Thread(
                target=self._read_loop, name=f'{self.frame_id}_reader', daemon=True
            )
            self._reader.start()
        except Exception:
            self.destroy_node()
            raise

        read_mode = 'on data arrival' if self.read_rate_hz == 0 else f'at {self.read_rate_hz} Hz'
        self.get_logger().info(
            f'Ultrasonic node initialized: {self.port} -> {self.range_topic}, '
            f'reading {read_mode}, publishing at {self.publish_rate_hz} Hz'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Typed declarations can return None if a YAML entry is missing.
        # Reading all declared parameters raises a clear ROS error in that case.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if self.endpoint_group not in ('ULTRASONIC_LEFT_NODE', 'ULTRASONIC_RIGHT_NODE'):
            raise ValueError(f'Unknown endpoint_group: {self.endpoint_group}')
        for name in ('timeout_s', 'publish_rate_hz', 'max_sample_age_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not math.isfinite(self.read_rate_hz) or self.read_rate_hz < 0:
            raise ValueError('read_rate_hz must be zero (on arrival) or finite and positive')
        if self.field_of_view_rad <= 0:
            raise ValueError('field_of_view_rad must be positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if not 0 <= self.min_range_m < self.max_range_m:
            raise ValueError('Invalid ultrasonic measurement range')

    # -----------------------
    #   Read independently and retain only the latest valid sample
    # -----------------------
    def _read_loop(self):
        period = 1.0 / self.read_rate_hz if self.read_rate_hz > 0 else 0.0
        while not self._stop.is_set():
            started = time.monotonic()
            success = self._read_distance(wait_for_data=(period == 0))
            # Back off on a disconnected device; never spin on repeated errors.
            delay = max(0.0, period - (time.monotonic() - started))
            if not success:
                delay = max(delay, self.timeout_s)
            self._stop.wait(delay)

    def _read_distance(self, wait_for_data):
        try:
            distance_mm = self.sensor.getDistance(wait_for_data=wait_for_data)
        except OSError as error:
            with self._sample_lock:
                self._latest_sample = None
            self.get_logger().warning(
                f'Ultrasonic read failed: {error}', throttle_duration_sec=5.0
            )
            return False

        if distance_mm is None and self.sensor.last_operate_status == self.sensor.STA_ERR_DATA:
            return True  # An idle timeout or partial frame is not a new sample.

        if self.sensor.last_operate_status != self.sensor.STA_OK:
            with self._sample_lock:
                self._latest_sample = None
            self.get_logger().warning(
                'Ultrasonic measurement rejected: '
                f'{self.sensor.last_operate_status}', throttle_duration_sec=5.0
            )
            return True

        # The wire protocol has no timestamp: this is the host decoding time,
        # not the exact physical measurement time. Monotonic time tracks expiry.
        sample = (distance_mm, self.get_clock().now().to_msg(), time.monotonic())
        with self._sample_lock:
            self._latest_sample = sample
        return True

    def publish_distance(self):
        with self._sample_lock:
            sample = self._latest_sample
        if sample is None:
            return
        distance_mm, stamp, received_at = sample
        # Check source time AND elapsed wall time: a paused ROS clock must not
        # keep a disconnected sensor fresh. Never mix the two clock domains.
        if (not is_fresh(stamp, self.get_clock().now(), self.max_sample_age_s)
                or not is_fresh(received_at, time.monotonic(), self.max_sample_age_s)):
            return

        msg = Range()
        # Repeating the latest value must not make an old measurement look new.
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.radiation_type = Range.ULTRASOUND
        msg.min_range = self.min_range_m
        msg.max_range = self.max_range_m
        msg.field_of_view = self.field_of_view_rad
        msg.range = distance_mm / 1000.0

        self.range_pub.publish(msg)

    # -----------------------
    #   Release the serial connection
    # -----------------------
    def destroy_node(self):
        self._stop.set()
        if self._reader is not None and self._reader.is_alive():
            # A finite serial timeout bounds the reader's idle wait.
            self._reader.join()
        if self.sensor is not None:
            self.sensor.close()
            self.sensor = None
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UltrasonicNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
