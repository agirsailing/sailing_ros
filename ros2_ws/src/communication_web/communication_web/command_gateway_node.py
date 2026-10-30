"""Expose recording and course-mark services to MQTT clients."""

import math
from queue import Empty, Full, Queue

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.parameter import Parameter
from sail_msgs.srv import PingMark, StartRecording, StopRecording

from communication_web.gateway.mqtt_client import MqttClientWrapper
from communication_web.gateway.recording_rpc import RecordingRpc
from communication_web.gateway.mark_rpc import MarkRpc
from communication_web.generated.ros_endpoints import Services, Topics


class CommandGatewayNode(Node):
    def __init__(self):
        super().__init__('command_gateway_node')

        # 1. Declare and validate request handling configuration.
        self.service_timeout_s = self.declare_parameter('service_timeout_s', Parameter.Type.DOUBLE).value
        self.process_rate_hz = self.declare_parameter('process_rate_hz', Parameter.Type.DOUBLE).value
        self.command_queue_size = self.declare_parameter('command_queue_size', Parameter.Type.INTEGER).value
        self.response_cache_size = self.declare_parameter('response_cache_size', Parameter.Type.INTEGER).value
        self.max_payload_bytes = self.declare_parameter('max_payload_bytes', Parameter.Type.INTEGER).value
        self._validate_parameters()
        self.commands = Queue(maxsize=self.command_queue_size)

        # 2. Explicit service routes; recording and ping requests are independent.
        sv = Services.COMMAND_GATEWAY_NODE.SRV
        mt = Topics.COMMAND_GATEWAY_NODE.MQTT
        self.start_client = self.create_client(StartRecording, sv.START_RECORDING)
        self.stop_client = self.create_client(StopRecording, sv.STOP_RECORDING)
        routes = {
            mt.SUB.START_RECORDING: (self.start_client, StartRecording.Request,
                                     mt.RSP.START_RECORDING, 'effective_bag_name'),
            mt.SUB.STOP_RECORDING: (self.stop_client, StopRecording.Request,
                                    mt.RSP.STOP_RECORDING, 'last_bag_name'),
        }
        self.ping_topic = mt.SUB.PING_MARK
        self.ping_client = self.create_client(PingMark, sv.PING_MARK)
        self.mqtt = MqttClientWrapper(
            self, (*routes, self.ping_topic), self._enqueue_command)
        self.recording_rpc = RecordingRpc(
            routes, self.mqtt.publish_json, self.service_timeout_s, self.response_cache_size)
        self.mark_rpc = MarkRpc(
            self.ping_client, PingMark.Request, self.mqtt.publish_json,
            mt.RSP.PING_MARK, self.service_timeout_s, self.response_cache_size)

        # 3. Paho only enqueues bytes. ROS service calls run on the ROS executor.
        # A steady timer keeps command timeouts working when ROS time is paused.
        self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.timer = self.create_timer(1.0 / self.process_rate_hz, self._process_commands,
                                      clock=self.wall_clock)
        self.mqtt.start()

    def _validate_parameters(self):
        self.get_parameters(self.list_parameters([], depth=0).names)
        for name in ('service_timeout_s', 'process_rate_hz'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        for name in ('command_queue_size', 'response_cache_size', 'max_payload_bytes'):
            if getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive')

    def _enqueue_command(self, topic, payload, retained):
        if retained:
            self.get_logger().warning('Ignoring retained command')
            return
        if len(payload) > self.max_payload_bytes:
            self.get_logger().warning('Ignoring oversized command')
            return
        try:
            self.commands.put_nowait((topic, payload, retained))
        except Full:
            self.get_logger().warning('Command queue is full')

    def _process_commands(self):
        self.recording_rpc.poll()
        self.mark_rpc.poll()
        for _ in range(self.command_queue_size):
            try:
                command = self.commands.get_nowait()
            except Empty:
                break
            if command[0] == self.ping_topic:
                self.mark_rpc.handle(command[1], command[2])
            else:
                self.recording_rpc.handle(*command)

    def destroy_node(self):
        self.mqtt.stop()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CommandGatewayNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
