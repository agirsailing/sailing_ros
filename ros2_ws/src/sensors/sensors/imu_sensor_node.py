# /ros2_ws/src/sensors/sensors/imu_sensor_node.py
"""Acquire BNO085 fused orientation and 9-DOF data over a USB-UART converter.

Named imu_sensor_node because data_elaboration already runs a node called
imu_node; ROS node names must be unique in the graph.
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu, MagneticField

from sensors.drivers.imu_driver import ImuDriver, UartTransport, ORIENTATION_REPORTS
from sensors.generated.ros_endpoints import Topics


class ImuSensorNode(Node):
    def __init__(self):
        super().__init__('imu_sensor_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.port = self.declare_parameter('port', Parameter.Type.STRING).value
        self.baudrate = self.declare_parameter('baudrate', Parameter.Type.INTEGER).value
        self.frame_id = self.declare_parameter('frame_id', Parameter.Type.STRING).value
        self.rate_hz = self.declare_parameter('rate_hz', Parameter.Type.DOUBLE).value
        self.report_rate_hz = self.declare_parameter('report_rate_hz', Parameter.Type.DOUBLE).value
        self.magnetometer_rate_hz = self.declare_parameter('magnetometer_rate_hz', Parameter.Type.DOUBLE).value
        self.orientation_report = self.declare_parameter('orientation_report', Parameter.Type.STRING).value
        self.roll_pitch_variance = self.declare_parameter('roll_pitch_variance_rad2', Parameter.Type.DOUBLE).value
        self.reset_delay_s = self.declare_parameter('reset_delay_s', Parameter.Type.DOUBLE).value
        self.stale_timeout_s = self.declare_parameter('stale_timeout_s', Parameter.Type.DOUBLE).value
        self.retry_interval_s = self.declare_parameter('retry_interval_s', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration before opening the serial port.
        self._validate_parameters()

        # 3. Internal state: the driver is (re)built on the timer so a missing
        # sensor is retried instead of stopping the node.
        self.transport = None
        self.driver = None
        self.retry_at_ns = 0
        self.last_accuracy = None

        # 4. Publishers.
        self.imu_pub = self.create_publisher(
            Imu,
            Topics.IMU_SENSOR_NODE.PUB.IMU_DATA,
            self.qos_depth
        )
        self.mag_pub = self.create_publisher(
            MagneticField,
            Topics.IMU_SENSOR_NODE.PUB.IMU_MAG,
            self.qos_depth
        )

        # 5. Reading and publishing timer.
        self.timer = self.create_timer(1.0 / self.rate_hz, self.publish_imu)

        self.get_logger().info(
            f'IMU node initialized on {self.port}, reading at {self.rate_hz:g} Hz')

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Typed declarations can return None if a YAML entry is missing.
        # Reading all declared parameters raises a clear ROS error in that case.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if not self.port.strip():
            raise ValueError('port must not be empty')
        if self.baudrate <= 0:
            raise ValueError('baudrate must be positive')
        if not self.frame_id.strip():
            raise ValueError('frame_id must not be empty')
        for name in ('rate_hz', 'reset_delay_s', 'stale_timeout_s', 'retry_interval_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not 0 < self.report_rate_hz <= 400:
            raise ValueError('report_rate_hz must lie in (0, 400]')
        if not 0 < self.magnetometer_rate_hz <= 100:
            raise ValueError('magnetometer_rate_hz must lie in (0, 100]')
        if self.orientation_report not in ORIENTATION_REPORTS:
            raise ValueError('orientation_report must be one of: ' + ', '.join(ORIENTATION_REPORTS))
        if not math.isfinite(self.roll_pitch_variance) or self.roll_pitch_variance < 0:
            raise ValueError('roll_pitch_variance_rad2 must be finite and nonnegative')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if self.rate_hz < self.report_rate_hz:
            self.get_logger().warning(
                'rate_hz is below report_rate_hz: reports queue up and add latency')

    # -----------------------
    #   Read and publish IMU measurements
    # -----------------------
    def publish_imu(self):
        now_ns = self.get_clock().now().nanoseconds
        if now_ns < self.retry_at_ns:
            return

        try:
            if self.driver is None:
                self.transport = UartTransport(self.port, self.baudrate)
                self.driver = ImuDriver(
                    self.transport,
                    1.0 / self.report_rate_hz,
                    1.0 / self.magnetometer_rate_hz,
                    self.orientation_report,
                    reset_delay_s=self.reset_delay_s,
                    stale_timeout_s=self.stale_timeout_s
                )
                self.last_accuracy = None
                self.get_logger().info(
                    f'BNO085 streaming {self.orientation_report} at {self.report_rate_hz:g} Hz')

            sample = self.driver.read()
        except Exception as error:
            self.get_logger().error(f'IMU acquisition failed: {error}')
            self._close()
            self.retry_at_ns = now_ns + int(self.retry_interval_s * 1e9)
            return

        if sample is None:
            return

        if sample.orientation_accuracy != self.last_accuracy:
            # 0 = unreliable .. 3 = high. Rotation-vector heading depends on
            # magnetometer calibration, which the sensor refines while moving.
            self.get_logger().info(
                f'IMU orientation accuracy status: {sample.orientation_accuracy}/3')
            self.last_accuracy = sample.orientation_accuracy

        stamp = self.get_clock().now().to_msg()
        msg = Imu()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id

        # Fused orientation of the sensor axes relative to the SH-2 world
        # (ENU, magnetic north for the rotation vector). Units: m/s^2, rad/s.
        x, y, z, w = sample.orientation
        msg.orientation.x = x
        msg.orientation.y = y
        msg.orientation.z = z
        msg.orientation.w = w
        msg.linear_acceleration.x = sample.acceleration[0]
        msg.linear_acceleration.y = sample.acceleration[1]
        msg.linear_acceleration.z = sample.acceleration[2]
        msg.angular_velocity.x = sample.angular_velocity[0]
        msg.angular_velocity.y = sample.angular_velocity[1]
        msg.angular_velocity.z = sample.angular_velocity[2]

        # Roll/pitch variance from YAML (0 = not characterized). Yaw uses the
        # sensor's own heading-accuracy estimate when the rotation vector is used.
        yaw_variance = (sample.heading_accuracy_rad ** 2
                        if math.isfinite(sample.heading_accuracy_rad) else 0.0)
        rp = self.roll_pitch_variance
        msg.orientation_covariance = [rp, 0.0, 0.0, 0.0, rp, 0.0, 0.0, 0.0, yaw_variance]
        # Zero covariance on acceleration and gyro: uncertainty unknown.
        self.imu_pub.publish(msg)

        if sample.magnetic_field is not None:
            mag = MagneticField()
            mag.header.stamp = stamp
            mag.header.frame_id = self.frame_id
            mag.magnetic_field.x = sample.magnetic_field[0]
            mag.magnetic_field.y = sample.magnetic_field[1]
            mag.magnetic_field.z = sample.magnetic_field[2]
            self.mag_pub.publish(mag)

    # -----------------------
    #   Release the serial port
    # -----------------------
    def _close(self):
        # Release the port before a retry reopens it.
        transport, self.transport, self.driver = self.transport, None, None
        if transport is not None:
            try:
                transport.close()
            except Exception as error:
                self.get_logger().warning(f'Closing IMU port failed: {error}')

    def destroy_node(self):
        self._close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ImuSensorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()