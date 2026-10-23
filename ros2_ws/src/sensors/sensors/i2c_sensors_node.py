# /ros2_ws/src/sensors/sensors/i2c_sensors_node.py
import math

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu, MagneticField
from geometry_msgs.msg import Vector3Stamped
from smbus2 import SMBus

from sensors.drivers.i2c_mux import I2CMultiplexer
from sensors.drivers.imu_driver import ImuDriver, ORIENTATION_REPORTS
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

        # IMU (BNO085) configuration. channel -1 = wired upstream of the mux.
        self.imu_enabled = self.declare_parameter('imu.enabled', Parameter.Type.BOOL).value
        self.imu_channel = self.declare_parameter('imu.channel', Parameter.Type.INTEGER).value
        self.imu_address = self.declare_parameter('imu.address', Parameter.Type.INTEGER).value
        self.imu_frame_id = self.declare_parameter('imu.frame_id', Parameter.Type.STRING).value
        self.imu_rate_hz = self.declare_parameter('imu.rate_hz', Parameter.Type.DOUBLE).value
        self.imu_report_rate_hz = self.declare_parameter('imu.report_rate_hz', Parameter.Type.DOUBLE).value
        self.imu_mag_rate_hz = self.declare_parameter('imu.magnetometer_rate_hz', Parameter.Type.DOUBLE).value
        self.imu_orientation_report = self.declare_parameter('imu.orientation_report', Parameter.Type.STRING).value
        self.imu_roll_pitch_variance = self.declare_parameter('imu.roll_pitch_variance_rad2', Parameter.Type.DOUBLE).value
        self.imu_reset_delay_s = self.declare_parameter('imu.reset_delay_s', Parameter.Type.DOUBLE).value
        self.imu_stale_timeout_s = self.declare_parameter('imu.stale_timeout_s', Parameter.Type.DOUBLE).value

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

        # 3. Internal state: each sensor has its own driver and retry deadline.
        self.imu_driver = None
        self.compass_driver = None
        self.imu_retry_at_ns = 0
        self.compass_retry_at_ns = 0
        self.imu_last_accuracy = None

        # 4. Open the shared bus and multiplexer.
        # Drivers hold the mux lock across channel selection, reading and
        # deselection. No other process may manually operate this multiplexer.
        self.mux = I2CMultiplexer(
            SMBus(self.bus_number),
            self.mux_address,
            self.mux_channel_count
        )

        try:
            # 5. Sensor publishers.
            if self.imu_enabled:
                self.imu_pub = self.create_publisher(
                    Imu,
                    Topics.I2C_SENSORS_NODE.PUB.IMU_DATA,
                    self.qos_depth
                )
                self.imu_mag_pub = self.create_publisher(
                    MagneticField,
                    Topics.I2C_SENSORS_NODE.PUB.IMU_MAG,
                    self.qos_depth
                )

            if self.compass_enabled:
                self.compass_pub = self.create_publisher(
                    Vector3Stamped,
                    Topics.I2C_SENSORS_NODE.PUB.COMPASS_DATA,
                    self.qos_depth
                )

            # 6. Independent reading and publishing timers.
            # Driver initialization happens on the first callback so a missing
            # sensor can be retried without preventing the other from running.
            if self.imu_enabled:
                self.imu_timer = self.create_timer(
                    1.0 / self.imu_rate_hz,
                    self.publish_imu
                )
            else:
                self.get_logger().info('IMU acquisition disabled')

            if self.compass_enabled:
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
        if self.imu_rate_hz <= 0:
            raise ValueError('imu.rate_hz must be positive')
        if not 0 < self.imu_report_rate_hz <= 400:
            raise ValueError('imu.report_rate_hz must lie in (0, 400]')
        if not 0 < self.imu_mag_rate_hz <= 100:
            raise ValueError('imu.magnetometer_rate_hz must lie in (0, 100]')
        if self.imu_orientation_report not in ORIENTATION_REPORTS:
            raise ValueError('imu.orientation_report must be one of: '
                             + ', '.join(ORIENTATION_REPORTS))
        if not math.isfinite(self.imu_roll_pitch_variance) or self.imu_roll_pitch_variance < 0:
            raise ValueError('imu.roll_pitch_variance_rad2 must be finite and nonnegative')
        if self.imu_reset_delay_s <= 0 or self.imu_stale_timeout_s <= 0:
            raise ValueError('imu.reset_delay_s and imu.stale_timeout_s must be positive')
        if self.compass_rate_hz <= 0:
            raise ValueError('compass.rate_hz must be positive')
        if self.compass_reset_delay_s <= 0:
            raise ValueError('compass.reset_delay_s must be positive')
        if self.compass_conversion_delay_s <= 0:
            raise ValueError('compass.conversion_delay_s must be positive')
        if not -1 <= self.imu_channel < self.mux_channel_count:
            raise ValueError('Invalid imu.channel: -1 (upstream of the mux) or a mux channel')
        if not 0 <= self.compass_channel < self.mux_channel_count:
            raise ValueError('Invalid compass.channel')
        if self.imu_rate_hz < self.imu_report_rate_hz:
            self.get_logger().warning(
                'imu.rate_hz is below imu.report_rate_hz: reports queue up and add latency')

    # -----------------------
    #   Read and publish IMU measurements
    # -----------------------
    def publish_imu(self):
        now_ns = self.get_clock().now().nanoseconds
        if now_ns < self.imu_retry_at_ns:
            return

        try:
            if self.imu_driver is None:
                self.imu_driver = ImuDriver(
                    self.mux,
                    self.imu_channel,
                    self.imu_address,
                    1.0 / self.imu_report_rate_hz,
                    1.0 / self.imu_mag_rate_hz,
                    self.imu_orientation_report,
                    reset_delay_s=self.imu_reset_delay_s,
                    stale_timeout_s=self.imu_stale_timeout_s
                )
                self.imu_last_accuracy = None
                self.get_logger().info(
                    f'BNO085 streaming {self.imu_orientation_report} at '
                    f'{self.imu_report_rate_hz:g} Hz')

            sample = self.imu_driver.read()
        except Exception as error:
            self.get_logger().error(f'IMU acquisition failed: {error}')
            self.imu_driver = None
            self.imu_retry_at_ns = now_ns + int(self.retry_interval_s * 1e9)
            return

        if sample is None:
            return

        if sample.orientation_accuracy != self.imu_last_accuracy:
            # 0 = unreliable .. 3 = high. Rotation-vector heading depends on
            # magnetometer calibration, which the sensor refines while moving.
            self.get_logger().info(
                f'IMU orientation accuracy status: {sample.orientation_accuracy}/3')
            self.imu_last_accuracy = sample.orientation_accuracy

        stamp = self.get_clock().now().to_msg()
        msg = Imu()
        msg.header.stamp = stamp
        msg.header.frame_id = self.imu_frame_id

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
        rp = self.imu_roll_pitch_variance
        msg.orientation_covariance = [rp, 0.0, 0.0, 0.0, rp, 0.0, 0.0, 0.0, yaw_variance]
        # Zero covariance on acceleration and gyro: uncertainty unknown.
        self.imu_pub.publish(msg)

        if sample.magnetic_field is not None:
            mag = MagneticField()
            mag.header.stamp = stamp
            mag.header.frame_id = self.imu_frame_id
            mag.magnetic_field.x = sample.magnetic_field[0]
            mag.magnetic_field.y = sample.magnetic_field[1]
            mag.magnetic_field.z = sample.magnetic_field[2]
            self.imu_mag_pub.publish(mag)

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
