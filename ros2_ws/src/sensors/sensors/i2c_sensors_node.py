"""Own the I2C multiplexer and publish independent IMU/compass measurements."""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Vector3Stamped
from smbus2 import SMBus

from .drivers.i2c_mux import I2CMultiplexer
from .drivers.imu_driver import ImuDriver
from .drivers.compass_driver import CompassDriver
from .generated.ros_endpoints import Topics
from .utils.configuration import depth, parameter, positive


class I2CSensorsNode(Node):
    def __init__(self):
        super().__init__('i2c_sensors_node')
        p = lambda name, kind: parameter(self, name, kind)
        bus = p('bus', Parameter.Type.INTEGER)
        address = p('mux_address', Parameter.Type.INTEGER)
        channels = p('mux_channel_count', Parameter.Type.INTEGER)
        self.retry_interval = positive(self, 'retry_interval_s')
        qos = depth(self)
        self.devices = {}
        self.sensor_timers = []
        # Default mutually-exclusive callbacks and the mux lock both protect
        # select/read/deselect. No other process may manually operate this mux.
        self.mux = I2CMultiplexer(SMBus(bus), address, channels)
        try:
            for name, cls, message, topic in (
                ('imu', ImuDriver, Imu, Topics.I2C_SENSORS_NODE.PUB.IMU_RAW),
                ('compass', CompassDriver, Vector3Stamped,
                 Topics.I2C_SENSORS_NODE.PUB.COMPASS_RAW),
            ):
                enabled = p(f'{name}.enabled', Parameter.Type.BOOL)
                channel = p(f'{name}.channel', Parameter.Type.INTEGER)
                addr = p(f'{name}.address', Parameter.Type.INTEGER)
                frame = p(f'{name}.frame_id', Parameter.Type.STRING)
                rate = positive(self, f'{name}.rate_hz')
                if not 0 <= channel < channels:
                    raise ValueError(f'Invalid {name} channel')
                if name == 'imu':
                    options = (
                        p('imu.odr_hz', Parameter.Type.DOUBLE),
                        p('imu.accel_range_g', Parameter.Type.INTEGER),
                        p('imu.gyro_range_dps', Parameter.Type.INTEGER))
                else:
                    options = (
                        p('compass.reset_value', Parameter.Type.INTEGER),
                        p('compass.measurement_value', Parameter.Type.INTEGER),
                        positive(self, 'compass.reset_delay_s'),
                        positive(self, 'compass.conversion_delay_s'))
                if not enabled:
                    continue
                self.devices[name] = {
                    'factory': lambda cls=cls, channel=channel, addr=addr, options=options:
                        cls(self.mux, channel, addr, *options),
                    'driver': None, 'frame': frame, 'retry_at': 0,
                    'publisher': self.create_publisher(message, topic, qos)}
                self.sensor_timers.append(self.create_timer(
                    1.0 / rate, lambda name=name: self.read(name)))
        except Exception:
            self.mux.close()
            raise

    def read(self, name):
        state = self.devices[name]
        now = self.get_clock().now().nanoseconds
        if now < state['retry_at']:
            return
        try:
            if state['driver'] is None:
                state['driver'] = state['factory']()
            values = state['driver'].read()
        except Exception as error:
            self.get_logger().error(f'{name} acquisition failed: {error}')
            state['driver'] = None
            state['retry_at'] = now + int(self.retry_interval * 1e9)
            return
        msg = Imu() if name == 'imu' else Vector3Stamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = state['frame']
        if name == 'imu':
            accel, gyro = values
            msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z = accel
            msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z = gyro
            # -1 means orientation is unavailable. Zero covariance for the
            # measured acceleration/gyro means uncertainty is unknown.
            msg.orientation_covariance[0] = -1.0
        else:
            msg.vector.x, msg.vector.y, msg.vector.z = map(float, values)
        state['publisher'].publish(msg)

    def destroy_node(self):
        self.mux.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = I2CSensorsNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
