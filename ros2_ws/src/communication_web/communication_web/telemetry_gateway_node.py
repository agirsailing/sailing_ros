"""Aggregate processed boat data and publish typed ROS messages and MQTT JSON."""

import math

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sail_msgs.msg import (
    BoatHeight, BoatPosition, GpsSummary, RecordingState, RollPitchYaw, WebTelemetry,
)
from std_msgs.msg import Bool

from communication_web.gateway.mqtt_client import MqttClientWrapper
from communication_web.gateway.telemetry import TelemetrySnapshot
from communication_web.generated.ros_endpoints import Topics


class TelemetryGatewayNode(Node):
    def __init__(self):
        super().__init__('telemetry_gateway_node')

        # 1. Declare and validate the snapshot configuration.
        self.publish_rate_hz = self.declare_parameter('publish_rate_hz', Parameter.Type.DOUBLE).value
        self.attitude_timeout_s = self.declare_parameter('attitude_timeout_s', Parameter.Type.DOUBLE).value
        self.height_timeout_s = self.declare_parameter('height_timeout_s', Parameter.Type.DOUBLE).value
        self.battery_timeout_s = self.declare_parameter('battery_timeout_s', Parameter.Type.DOUBLE).value
        self.gps_timeout_s = self.declare_parameter('gps_timeout_s', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value
        self._validate_parameters()
        self.snapshot = TelemetrySnapshot(
            self.attitude_timeout_s, self.height_timeout_s,
            self.battery_timeout_s, self.gps_timeout_s)
        self.rt = Topics.TELEMETRY_GATEWAY_NODE
        self.mqtt = MqttClientWrapper(self)

        # 2. The same structured snapshot is available to ROS and the web app.
        self.telemetry_pub = self.create_publisher(
            WebTelemetry, self.rt.PUB.TELEMETRY, self.qos_depth)
        self.position_pub = self.create_publisher(
            BoatPosition, self.rt.PUB.POSITION, self.qos_depth)

        # 3. Consume processed data; aerospace angles are already in degrees.
        self.attitude_sub = self.create_subscription(
            RollPitchYaw, self.rt.SUB.ATTITUDE,
            lambda msg: self._receive('attitude', msg), self.qos_depth)
        self.height_sub = self.create_subscription(
            BoatHeight, self.rt.SUB.HEIGHT,
            lambda msg: self._receive('height', msg), self.qos_depth)
        self.battery_sub = self.create_subscription(
            Bool, self.rt.SUB.BATTERY,
            lambda msg: self._receive('battery', msg), self.qos_depth)
        self.gps_sub = self.create_subscription(
            GpsSummary, self.rt.SUB.GPS,
            lambda msg: self._receive('gps', msg), self.qos_depth)
        self.recording_sub = self.create_subscription(
            RecordingState, self.rt.SUB.RECORDING_STATE,
            self._publish_recording_state, self.qos_depth)

        # 4. Publish periodic snapshots and start the asynchronous MQTT loop.
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self.publish_snapshot)
        self.mqtt.start()

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        for name in ('publish_rate_hz', 'attitude_timeout_s', 'height_timeout_s',
                     'battery_timeout_s', 'gps_timeout_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    def _receive(self, name, message):
        self.snapshot.update(name, message, self.get_clock().now().nanoseconds / 1e9)

    def publish_snapshot(self):
        now = self.get_clock().now()
        data, location, gps_stamp = self.snapshot.build(now.nanoseconds / 1e9)
        telemetry = WebTelemetry()
        telemetry.header.stamp = now.to_msg()
        for name, value in data.items():
            setattr(telemetry, name, value)
        position = BoatPosition()
        position.header.stamp = now.to_msg()
        if gps_stamp is not None:
            position.gps_stamp = gps_stamp
        for name, value in location.items():
            setattr(position, name, value)
        self.telemetry_pub.publish(telemetry)
        self.position_pub.publish(position)
        self.mqtt.publish_ros_msg(self.rt.MQTT.PUB.TELEMETRY, telemetry)
        self.mqtt.publish_ros_msg(self.rt.MQTT.PUB.POSITION, position)

    def _publish_recording_state(self, message):
        # Periodic manager state; no retained copy that could survive the manager.
        self.mqtt.publish_ros_msg(self.rt.MQTT.PUB.RECORDING_STATE, message)

    def destroy_node(self):
        self.mqtt.stop()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = TelemetryGatewayNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
