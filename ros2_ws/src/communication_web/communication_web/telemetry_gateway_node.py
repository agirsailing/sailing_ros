"""Aggregate processed boat data and publish typed ROS messages and MQTT JSON."""

import math
import time

from gps_msgs.msg import GPSFix
from marti_common_msgs.msg import Float64Stamped
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sail_common.freshness import is_fresh
from sail_msgs.msg import (
    BatteryData, MapDataMsg, Mark, RecordingState, DashboardDataMsg,
)
from sail_msgs.srv import PingMark
from sensor_msgs.msg import Imu, Range

from communication_web.gateway.mqtt_client import MqttClientWrapper
from communication_web.gateway.telemetry import TelemetrySnapshot
from communication_web.generated.ros_endpoints import Services, Topics


class TelemetryGatewayNode(Node):
    def __init__(self):
        super().__init__('telemetry_gateway_node')

        # 1. Declare and validate the snapshot configuration.
        self.dashboard_publish_rate_hz = self.declare_parameter(
            'dashboard_publish_rate_hz', Parameter.Type.DOUBLE).value
        self.map_publish_rate_hz = self.declare_parameter(
            'map_publish_rate_hz', Parameter.Type.DOUBLE).value
        self.recording_state_publish_rate_hz = self.declare_parameter(
            'recording_state_publish_rate_hz', Parameter.Type.DOUBLE).value
        self.recording_state_timeout_s = self.declare_parameter(
            'recording_state_timeout_s', Parameter.Type.DOUBLE).value
        self.attitude_timeout_s = self.declare_parameter('attitude_timeout_s', Parameter.Type.DOUBLE).value
        self.height_timeout_s = self.declare_parameter('height_timeout_s', Parameter.Type.DOUBLE).value
        self.battery_timeout_s = self.declare_parameter('battery_timeout_s', Parameter.Type.DOUBLE).value
        self.gps_timeout_s = self.declare_parameter('gps_timeout_s', Parameter.Type.DOUBLE).value
        self.ultrasonic_timeout_s = self.declare_parameter('ultrasonic_timeout_s', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value
        self._validate_parameters()
        self.recording_sample = None
        # Course state belongs to the boat, not to a browser session.
        # One mark per type, retained until this node restarts or it is replaced.
        self.marks = {}
        self.snapshot = TelemetrySnapshot(
            self.attitude_timeout_s, self.height_timeout_s,
            self.battery_timeout_s, self.gps_timeout_s, self.ultrasonic_timeout_s)
        self.rt = Topics.TELEMETRY_GATEWAY_NODE
        self.mqtt = MqttClientWrapper(self)

        # 2. The same structured snapshot is available to ROS and the web app.
        self.telemetry_pub = self.create_publisher(
            DashboardDataMsg, self.rt.PUB.TELEMETRY, self.qos_depth)
        self.position_pub = self.create_publisher(
            MapDataMsg, self.rt.PUB.POSITION, self.qos_depth)
        self.ping_service = self.create_service(
            PingMark, Services.TELEMETRY_GATEWAY_NODE.SRV.PING_MARK, self._ping_mark)

        # 3. Consume sensor snapshots and processed attitude/height directly.
        self.attitude_sub = self.create_subscription(
            Imu, self.rt.SUB.ATTITUDE,
            lambda msg: self._receive('attitude', msg), self.qos_depth)
        self.height_sub = self.create_subscription(
            Float64Stamped, self.rt.SUB.HEIGHT,
            lambda msg: self._receive('height', msg), self.qos_depth)
        self.battery_sub = self.create_subscription(
            BatteryData, self.rt.SUB.BATTERY,
            lambda msg: self._receive('battery', msg), self.qos_depth)
        self.gps_sub = self.create_subscription(
            GPSFix, self.rt.SUB.GPS,
            lambda msg: self._receive('gps', msg), self.qos_depth)
        self.recording_sub = self.create_subscription(
            RecordingState, self.rt.SUB.RECORDING_STATE,
            self._receive_recording_state, self.qos_depth)
        self.ultrasonic_left_sub = self.create_subscription(
            Range, self.rt.SUB.ULTRASONIC_LEFT,
            lambda msg: self._receive('ultrasonic_left', msg), self.qos_depth)
        self.ultrasonic_right_sub = self.create_subscription(
            Range, self.rt.SUB.ULTRASONIC_RIGHT,
            lambda msg: self._receive('ultrasonic_right', msg), self.qos_depth)

        # 4. Publish periodic snapshots and start the asynchronous MQTT loop.
        self.dashboard_timer = self.create_timer(
            1.0 / self.dashboard_publish_rate_hz, self.publish_dashboard)
        self.map_timer = self.create_timer(
            1.0 / self.map_publish_rate_hz, self.publish_map)
        self.recording_state_timer = self.create_timer(
            1.0 / self.recording_state_publish_rate_hz, self._publish_recording_state)
        self.mqtt.start()

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        for name in ('dashboard_publish_rate_hz', 'map_publish_rate_hz',
                     'recording_state_publish_rate_hz', 'recording_state_timeout_s',
                     'attitude_timeout_s', 'height_timeout_s',
                     'battery_timeout_s', 'gps_timeout_s', 'ultrasonic_timeout_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    def _receive(self, name, message):
        self.snapshot.update(name, message, self.get_clock().now().nanoseconds / 1e9)

    def publish_dashboard(self):
        now = self.get_clock().now()
        data, _, _ = self.snapshot.build(now.nanoseconds / 1e9)
        telemetry = DashboardDataMsg()
        telemetry.header.stamp = now.to_msg()
        for name, value in data.items():
            setattr(telemetry, name, value)
        self.telemetry_pub.publish(telemetry)
        self.mqtt.publish_ros_msg(self.rt.MQTT.PUB.TELEMETRY, telemetry)

    def publish_map(self):
        now = self.get_clock().now()
        _, location, gps_stamp = self.snapshot.build(now.nanoseconds / 1e9)
        position = MapDataMsg()
        position.header.stamp = now.to_msg()
        if gps_stamp is not None:
            position.gps_stamp = gps_stamp
        for name, value in location.items():
            setattr(position, name, value)
        position.marks = [self.marks[kind] for kind in sorted(self.marks)]
        self.position_pub.publish(position)
        self.mqtt.publish_ros_msg(self.rt.MQTT.PUB.POSITION, position)

    def _ping_mark(self, request, response):
        if request.type not in (Mark.COMMITTEE, Mark.PIN, Mark.WINDWARD):
            response.success = False
            response.error_message = 'Unknown mark type'
            return response
        now = self.get_clock().now().nanoseconds / 1e9
        gps = self.snapshot.gps_position(now)
        # SOG is not needed to capture a geographical position.
        if gps is None:
            response.success = False
            response.error_message = 'No fresh valid GPS fix; mark unchanged'
            return response
        mark = Mark()
        mark.header = gps.header
        mark.type = request.type
        mark.lat, mark.lon = gps.latitude, gps.longitude
        self.marks[mark.type] = mark
        response.success = True
        response.error_message = ''
        response.mark = mark
        return response

    def _receive_recording_state(self, message):
        # Operational state has no source header; only receipt freshness is known.
        self.recording_sample = (message, time.monotonic())

    def _publish_recording_state(self):
        if self.recording_sample is None:
            return
        message, received_at = self.recording_sample
        if not is_fresh(received_at, time.monotonic(), self.recording_state_timeout_s):
            self.recording_sample = None
            return
        # The independent MQTT timer sends only the latest live state, without
        # renewing its receipt time or replaying a backlog of ROS state updates.
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
