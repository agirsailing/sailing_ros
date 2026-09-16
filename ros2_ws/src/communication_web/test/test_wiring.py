"""Exercise node wiring with fake ROS/MQTT objects and the checked-in config."""

import ast
import json
import math
from pathlib import Path
from queue import Empty, Full, Queue
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from communication_web.gateway.recording_rpc import RecordingRpc
from communication_web.gateway.telemetry import TelemetrySnapshot, json_safe
from communication_web.generated.ros_endpoints import Services, Topics


def mapping_file(path):
    """Read only the scalar/mapping YAML subset used by these two config files.

    This is an offline test helper, not a general YAML parser or runtime loader.
    """
    root = {}
    stack = [(-1, root)]
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, value = line.split(':', 1)
        while stack[-1][0] >= indent:
            stack.pop()
        if not value.strip():
            item = {}
            stack[-1][1][key] = item
            stack.append((indent, item))
        else:
            stack[-1][1][key] = json.loads(value.strip())
    return root


def flatten(mapping, prefix=''):
    values = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            values.update(flatten(value, prefix + key + '.'))
        else:
            values[prefix + key] = value
    return values


def message_type(name):
    # Strict fields from the actual .msg file, without invoking ROS generators.
    fields = []
    for line in (ROOT.parent / 'sail_msgs' / 'msg' / (name + '.msg')).read_text().splitlines():
        line = line.split('#')[0].strip()
        if not line or '=' in line:
            continue
        fields.append(line.split())

    def init(self):
        for kind, field in fields:
            if kind == 'std_msgs/Header':
                value = NS(stamp=NS(sec=0, nanosec=0), frame_id='')
            elif kind == 'builtin_interfaces/Time':
                value = NS(sec=0, nanosec=0)
            elif kind == 'bool':
                value = False
            elif kind == 'string':
                value = ''
            else:
                value = 0.0
            setattr(self, field, value)

    return type(name, (), {'__slots__': tuple(field for _, field in fields), '__init__': init})


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.config = flatten(mapping_file(ROOT / 'config/params.yaml')[name]['ros__parameters'])
        self.declared = set()
        self.subscriptions = {}
        self.publishers = {}
        self.clients = {}

    def declare_parameter(self, name, kind):
        value = self.config[name]
        assert type(value) is kind, (name, kind, value)
        self.declared.add(name)
        return NS(value=value)

    def list_parameters(self, *args, **kwargs):
        return NS(names=list(self.declared))

    def get_parameters(self, names):
        return [self.config[name] for name in names]

    def get_logger(self):
        return Mock()

    def get_clock(self):
        return NS(now=lambda: NS(nanoseconds=100_000_000_000,
                                 to_msg=lambda: NS(sec=100, nanosec=0)))

    def create_subscription(self, kind, topic, callback, qos):
        self.subscriptions[topic] = callback
        return Mock()

    def create_publisher(self, kind, topic, qos):
        pub = Mock()
        self.publishers[topic] = pub
        return pub

    def create_client(self, kind, service):
        client = Mock()
        self.clients[service] = client
        return client

    def create_timer(self, *args, **kwargs):
        return Mock()


def load_class(path, name, **scope):
    # Execute only the class definition; imports and main() are never run.
    tree = ast.parse(path.read_text(encoding='utf-8'))
    definition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.fake_mqtt = NS(Client=Mock(), CallbackAPIVersion=NS(VERSION2=2), MQTTv311=4)
        self.parameter = NS(Type=NS(STRING=str, INTEGER=int, DOUBLE=float, BOOL=bool))
        self.transport = load_class(
            ROOT / 'communication_web/gateway/mqtt_client.py', 'MqttClientWrapper',
            json=json, uuid=uuid, mqtt=self.fake_mqtt, Parameter=self.parameter,
            json_safe=json_safe, message_to_ordereddict=lambda msg: {'test': float('nan')})
        self.messages = {name: message_type(name) for name in (
            'BoatHeight', 'BoatPosition', 'GpsSummary', 'RecordingState',
            'RollPitchYaw', 'WebTelemetry')}

    def telemetry_node(self):
        cls = load_class(
            ROOT / 'communication_web/telemetry_gateway_node.py', 'TelemetryGatewayNode',
            Node=FakeNode, math=math, Parameter=self.parameter,
            Topics=Topics, MqttClientWrapper=self.transport,
            TelemetrySnapshot=TelemetrySnapshot, Bool=NS, **self.messages)
        return cls()

    def command_node(self):
        cls = load_class(
            ROOT / 'communication_web/command_gateway_node.py', 'CommandGatewayNode',
            Node=FakeNode, math=math, Parameter=self.parameter, Queue=Queue,
            Empty=Empty, Full=Full, Clock=Mock(), ClockType=NS(STEADY_TIME=3),
            Topics=Topics, Services=Services, MqttClientWrapper=self.transport,
            RecordingRpc=RecordingRpc, StartRecording=NS(Request=object),
            StopRecording=NS(Request=object))
        return cls()

    def test_telemetry_constructor_parameters_and_real_message_fields(self):
        node = self.telemetry_node()
        self.assertEqual(set(node.config) - {'use_sim_time'}, node.declared)
        rt = Topics.TELEMETRY_GATEWAY_NODE
        self.assertEqual(len(node.subscriptions), 5)
        angle = self.messages['RollPitchYaw']()
        angle.header.stamp.sec = 100
        angle.roll_deg, angle.pitch_deg, angle.yaw_deg = 12.0, 3.0, 75.0
        node.subscriptions[rt.SUB.ATTITUDE](angle)
        node.publish_snapshot()
        message = node.publishers[rt.PUB.TELEMETRY].publish.call_args.args[0]
        self.assertEqual(message.header.stamp.sec, 100)
        self.assertEqual(message.roll_deg, 12.0)
        self.assertTrue(message.attitude_valid)
        position = node.publishers[rt.PUB.POSITION].publish.call_args.args[0]
        self.assertFalse(position.fix_valid)
        self.assertTrue(math.isnan(position.latitude_deg))

    def test_command_constructor_only_recording_and_queue_handoff(self):
        node = self.command_node()
        self.assertEqual(set(node.config), node.declared)
        self.assertEqual(set(node.clients), {
            Services.Shared.START_RECORDING, Services.Shared.STOP_RECORDING})
        mt = Topics.COMMAND_GATEWAY_NODE.MQTT
        node.mqtt.connected = True
        client = node.start_client
        client.service_is_ready.return_value = True
        client.call_async.return_value.done.return_value = False
        node._enqueue_command(mt.SUB.START_RECORDING, b'{"requestId":"abc"}', False)
        client.call_async.assert_not_called()
        node._process_commands()
        client.call_async.assert_called_once()
        node._enqueue_command(mt.SUB.STOP_RECORDING, b'{}', True)
        self.assertTrue(node.commands.empty())

    def test_transport_connects_asynchronously_and_resubscribes(self):
        node = self.command_node()
        transport = node.mqtt
        client = transport.client
        client.connect_async.assert_called_once_with('localhost', 1883, 60)
        client.loop_start.assert_called_once()
        transport._on_connect(client, None, None, NS(is_failure=False), None)
        self.assertEqual(client.subscribe.call_count, 2)
        transport._on_disconnect(client, None, None, None, None)
        self.assertFalse(transport.connected)
        transport._on_connect(client, None, None, NS(is_failure=False), None)
        self.assertEqual(client.subscribe.call_count, 4)

    def test_transport_emits_strict_json_and_no_retained_output(self):
        node = self.telemetry_node()
        transport = node.mqtt
        transport.connected = True
        transport.publish_json('test-output', {'value': float('nan')})
        args, kwargs = transport.client.publish.call_args
        self.assertEqual(json.loads(args[1]), {'value': None})
        self.assertFalse(kwargs['retain'])

    def test_yaml_and_generated_constants_match(self):
        data = mapping_file(ROOT / 'config/endpoints.yaml')
        for registry, cls in (('topics', Topics), ('services', Services)):
            for key, value in data[registry].items():
                self.assertEqual(getattr(cls.Shared, key.upper()), value)
        for name, node in data['nodes'].items():
            for direction, endpoints in node.items():
                cls = getattr(Services if direction == 'srv' else Topics, name.upper())
                block = getattr(cls, direction.upper())
                if direction == 'mqtt':
                    for subdirection, mapping in endpoints.items():
                        for key, value in mapping.items():
                            self.assertEqual(getattr(getattr(block, subdirection.upper()), key.upper()),
                                             data['topics'][value[1:]])
                else:
                    for key, value in endpoints.items():
                        registry = data['services'] if direction == 'srv' else data['topics']
                        self.assertEqual(getattr(block, key.upper()), registry[value[1:]])

    def test_inputs_match_existing_producer_constants(self):
        # Read simple generated modules only; no producer node or hardware code.
        def constants(package):
            scope = {}
            path = ROOT.parent / package / package / 'generated/ros_endpoints.py'
            exec(compile(path.read_text(), str(path), 'exec'), scope)
            return scope
        processing = constants('data_elaboration')['Topics']
        recorder = constants('rosbag_manager')
        rt = Topics.TELEMETRY_GATEWAY_NODE
        self.assertEqual(rt.SUB.ATTITUDE, processing.IMU_NODE.PUB.RPY_AERO)
        self.assertEqual(rt.SUB.HEIGHT, processing.ULTRASONIC_FILTER_NODE.PUB.HEIGHT)
        self.assertEqual(rt.SUB.BATTERY, processing.BATTERY_MONITOR_NODE.PUB.BATTERY_LOW)
        self.assertEqual(rt.SUB.GPS, processing.HEADING_NODE.PUB.GPS_SUMMARY)
        self.assertEqual(rt.SUB.RECORDING_STATE,
                         recorder['Topics'].ROSBAG_MANAGER_NODE.PUB.RECORDING_STATE)
        for name in ('START_RECORDING', 'STOP_RECORDING'):
            self.assertEqual(getattr(Services.COMMAND_GATEWAY_NODE.SRV, name),
                             getattr(recorder['Services'].ROSBAG_MANAGER_NODE.SRV, name))


if __name__ == '__main__':
    unittest.main()
