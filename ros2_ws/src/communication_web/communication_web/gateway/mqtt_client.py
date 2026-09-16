"""Shared MQTT transport for the two gateways, following the Polimi layout."""

import json
import uuid

import paho.mqtt.client as mqtt
from rclpy.parameter import Parameter
from rosidl_runtime_py.convert import message_to_ordereddict

from communication_web.gateway.telemetry import json_safe


class MqttClientWrapper:
    def __init__(self, node, subscriptions=(), on_message=None):
        self.node = node
        self.broker = node.declare_parameter('mqtt.broker', Parameter.Type.STRING).value
        self.port = node.declare_parameter('mqtt.port', Parameter.Type.INTEGER).value
        self.user = node.declare_parameter('mqtt.user', Parameter.Type.STRING).value
        self.password = node.declare_parameter('mqtt.password', Parameter.Type.STRING).value
        self.client_id = node.declare_parameter('mqtt.client_id', Parameter.Type.STRING).value
        self.keepalive = node.declare_parameter('mqtt.keepalive_s', Parameter.Type.INTEGER).value
        self.tls_enabled = node.declare_parameter('mqtt.tls_enabled', Parameter.Type.BOOL).value
        self.ca_file = node.declare_parameter('mqtt.ca_file', Parameter.Type.STRING).value
        self.qos = node.declare_parameter('mqtt.qos', Parameter.Type.INTEGER).value
        self.reconnect_min = node.declare_parameter('mqtt.reconnect_min_s', Parameter.Type.INTEGER).value
        self.reconnect_max = node.declare_parameter('mqtt.reconnect_max_s', Parameter.Type.INTEGER).value
        self.queue_size = node.declare_parameter('mqtt.max_queued_messages', Parameter.Type.INTEGER).value
        self._validate_parameters()
        self.subscriptions = subscriptions
        self.on_message = on_message
        self.connected = False
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f'{self.client_id}_{uuid.uuid4().hex[:8]}',
            protocol=mqtt.MQTTv311)
        self.client.max_queued_messages_set(self.queue_size)
        self.client.reconnect_delay_set(self.reconnect_min, self.reconnect_max)
        if self.user or self.password:
            self.client.username_pw_set(self.user, self.password)
        if self.tls_enabled:
            # Verify the broker certificate and hostname, using system CAs by default.
            self.client.tls_set(ca_certs=self.ca_file or None)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _validate_parameters(self):
        self.node.get_parameters(self.node.list_parameters([], depth=0).names)
        if not self.broker.strip() or not self.client_id.strip():
            raise ValueError('mqtt.broker and mqtt.client_id must not be empty')
        if not 1 <= self.port <= 65535 or self.keepalive <= 0:
            raise ValueError('Invalid MQTT port or keepalive')
        if self.qos not in (0, 1, 2) or self.queue_size <= 0:
            raise ValueError('Invalid MQTT QoS or queue size')
        if not 0 < self.reconnect_min <= self.reconnect_max:
            raise ValueError('Invalid MQTT reconnect interval')

    def start(self):
        # The network loop retries even if the broker is absent at startup.
        self.client.connect_async(self.broker, self.port, self.keepalive)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if not self.connected:
            self.node.get_logger().error(f'MQTT connection rejected: {reason_code}')
            return
        for topic in self.subscriptions:
            client.subscribe(topic, qos=self.qos)
        self.node.get_logger().info('MQTT connected')

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def _on_message(self, client, userdata, message):
        if self.on_message is not None:
            self.on_message(message.topic, bytes(message.payload), message.retain)

    def publish_json(self, topic, payload):
        if not self.connected:
            return
        self.client.publish(topic, json.dumps(json_safe(payload), allow_nan=False),
                            qos=self.qos, retain=False)

    def publish_ros_msg(self, topic, message):
        self.publish_json(topic, message_to_ordereddict(message))
