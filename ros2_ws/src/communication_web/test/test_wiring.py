"""Exercise node wiring with fake ROS/MQTT objects and the checked-in config."""

import ast
import json
import math
from pathlib import Path
from queue import Empty, Full, Queue
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'sail_common'))
from communication_web.gateway.recording_rpc import RecordingRpc
from communication_web.gateway.mark_rpc import MarkRpc
from communication_web.gateway.telemetry import TelemetrySnapshot, json_safe
from communication_web.generated.ros_endpoints import Services, Topics
from sail_common.freshness import is_fresh


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
            elif kind.endswith('[]'):
                value = []
            else:
                value = 0.0
            setattr(self, field, value)

    return type(name, (), {'__slots__': tuple(field for _, field in fields), '__init__': init})


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.config = flatten(mapping_file(ROOT / 'config/params.yaml')[name]['ros__parameters'])
        self.config.update(flatten(
            mapping_file(ROOT / 'config/mqtt_config.example.yaml')[name]['ros__parameters']))
        self.declared = set()
        self.subscriptions = {}
        self.publishers = {}
        self.clients = {}
        self.timers = []

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

    def create_service(self, kind, service, callback):
        return callback

    def create_timer(self, *args, **kwargs):
        self.timers.append(args)
        return Mock()


def load_class(path, name, **scope):
    # Execute only the class definition; imports and main() are never run.
    tree = ast.parse(path.read_text(encoding='utf-8'))
    definition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.monotonic = Mock(return_value=100.0)
        self.fake_mqtt = NS(Client=Mock(), CallbackAPIVersion=NS(VERSION2=2), MQTTv311=4)
        self.parameter = NS(Type=NS(STRING=str, INTEGER=int, DOUBLE=float, BOOL=bool))
        self.transport = load_class(
            ROOT / 'communication_web/gateway/mqtt_client.py', 'MqttClientWrapper',
            json=json, uuid=uuid, mqtt=self.fake_mqtt, Parameter=self.parameter,
            json_safe=json_safe, message_to_ordereddict=lambda msg: {'test': float('nan')})
        self.messages = {name: message_type(name) for name in (
            'BatteryData', 'MapDataMsg', 'RecordingState',
            'DashboardDataMsg', 'Mark')}
        self.messages['Mark'].COMMITTEE = 0
        self.messages['Mark'].PIN = 1
        self.messages['Mark'].WINDWARD = 2

    def telemetry_node(self, **rates):
        cls = load_class(
            ROOT / 'communication_web/telemetry_gateway_node.py', 'TelemetryGatewayNode',
            Node=FakeNode, math=math, Parameter=self.parameter,
            time=NS(monotonic=self.monotonic), is_fresh=is_fresh,
            Topics=Topics, Services=Services, PingMark=NS, MqttClientWrapper=self.transport,
            TelemetrySnapshot=TelemetrySnapshot, GPSFix=NS, Float64Stamped=NS, Imu=NS, Range=NS, **self.messages)
        original = FakeNode.declare_parameter

        def declare(node, name, kind):
            if name in rates:
                node.config[name] = rates[name]
            return original(node, name, kind)

        with patch.object(FakeNode, 'declare_parameter', declare):
            return cls()

    def command_node(self):
        cls = load_class(
            ROOT / 'communication_web/command_gateway_node.py', 'CommandGatewayNode',
            Node=FakeNode, math=math, Parameter=self.parameter, Queue=Queue,
            Empty=Empty, Full=Full, Clock=Mock(), ClockType=NS(STEADY_TIME=3),
            Topics=Topics, Services=Services, MqttClientWrapper=self.transport,
            RecordingRpc=RecordingRpc, StartRecording=NS(Request=object),
            StopRecording=NS(Request=object), MarkRpc=MarkRpc, PingMark=NS(Request=NS))
        return cls()

    def test_telemetry_constructor_parameters_and_real_message_fields(self):
        node = self.telemetry_node()
        self.assertEqual(set(node.config) - {'use_sim_time'}, node.declared)
        rt = Topics.TELEMETRY_GATEWAY_NODE
        self.assertEqual(len(node.subscriptions), 7)
        angle = NS(header=NS(stamp=NS(sec=100, nanosec=0)),
                   orientation=NS(x=0.0, y=0.0, z=math.sin(math.radians(75)/2),
                                  w=math.cos(math.radians(75)/2)),
                   orientation_covariance=[0.0] * 9)
        node.subscriptions[rt.SUB.ATTITUDE](angle)
        node.subscriptions[rt.SUB.HEIGHT](NS(
            header=NS(stamp=NS(sec=100, nanosec=0)), value=-0.05))
        node.subscriptions[rt.SUB.GPS](NS(
            header=NS(stamp=NS(sec=100, nanosec=0)), status=NS(status=0),
            latitude=59.3, longitude=18.1, speed=1.5, track=270.0))
        battery = self.messages['BatteryData']()
        battery.header.stamp.sec = 100
        battery.voltage_v, battery.low = 12.4, True
        node.subscriptions[rt.SUB.BATTERY](battery)
        node.subscriptions[rt.SUB.ULTRASONIC_LEFT](NS(
            header=NS(stamp=NS(sec=100, nanosec=0)), range=0.6, min_range=0.03, max_range=4.5))
        node.subscriptions[rt.SUB.ULTRASONIC_RIGHT](NS(
            header=NS(stamp=NS(sec=100, nanosec=0)), range=0.8, min_range=0.03, max_range=4.5))
        node.publish_dashboard()
        node.publish_map()
        message = node.publishers[rt.PUB.TELEMETRY].publish.call_args.args[0]
        self.assertEqual(message.header.stamp.sec, 100)
        self.assertAlmostEqual(message.roll_deg, 0.0)
        self.assertTrue(message.attitude_valid)
        self.assertTrue(message.height_valid)
        self.assertEqual(message.height_m, -0.05)
        self.assertTrue(message.battery_valid)
        self.assertTrue(message.battery_low)
        self.assertEqual(message.battery_voltage_v, 12.4)
        self.assertTrue(message.ultrasonic_left_valid)
        self.assertTrue(message.ultrasonic_right_valid)
        self.assertEqual(message.ultrasonic_left_m, 0.6)
        self.assertEqual(message.ultrasonic_right_m, 0.8)
        position = node.publishers[rt.PUB.POSITION].publish.call_args.args[0]
        self.assertTrue(position.fix_valid)
        self.assertEqual(position.latitude_deg, 59.3)
        self.assertEqual(position.sog_mps, 1.5)
        self.assertEqual(position.gps_stamp.sec, 100)
        self.assertAlmostEqual(message.yaw_deg, 75.0)
        self.assertEqual(message.sog_mps, 1.5)

    def test_independent_output_timers_and_recording_forwarding(self):
        node = self.telemetry_node(dashboard_publish_rate_hz=5.0, map_publish_rate_hz=2.0)
        self.assertEqual([(period, callback.__name__) for period, callback in node.timers],
                         [(0.2, 'publish_dashboard'), (0.5, 'publish_map'),
                          (2.0, '_publish_recording_state')])
        rt = Topics.TELEMETRY_GATEWAY_NODE
        node.mqtt.publish_ros_msg = Mock()
        for _ in range(3):
            node.timers[0][1]()
        self.assertEqual(node.telemetry_pub.publish.call_count, 3)
        node.position_pub.publish.assert_not_called()
        self.assertEqual([c.args[0] for c in node.mqtt.publish_ros_msg.call_args_list],
                         [rt.MQTT.PUB.TELEMETRY] * 3)
        node.timers[1][1]()
        self.assertEqual(node.telemetry_pub.publish.call_count, 3)
        node.position_pub.publish.assert_called_once()
        self.assertEqual(node.mqtt.publish_ros_msg.call_args.args[0], rt.MQTT.PUB.POSITION)
        recording = self.messages['RecordingState']()
        previous_calls = node.mqtt.publish_ros_msg.call_count
        node.subscriptions[rt.SUB.RECORDING_STATE](recording)
        self.assertEqual(node.mqtt.publish_ros_msg.call_count, previous_calls)
        node.timers[2][1]()
        node.mqtt.publish_ros_msg.assert_called_with(rt.MQTT.PUB.RECORDING_STATE, recording)
        self.assertEqual(node.telemetry_pub.publish.call_count, 3)
        node.position_pub.publish.assert_called_once()

    def test_output_rates_must_be_finite_and_positive(self):
        for name in ('dashboard_publish_rate_hz', 'map_publish_rate_hz',
                     'recording_state_publish_rate_hz', 'recording_state_timeout_s'):
            for value in (0.0, -1.0, math.inf, math.nan):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, name):
                        self.telemetry_node(**{name: value})

    def test_recording_mqtt_uses_latest_state_without_keeping_dead_manager_alive(self):
        node = self.telemetry_node()
        node.mqtt.publish_ros_msg = Mock()
        rt = Topics.TELEMETRY_GATEWAY_NODE
        node._publish_recording_state()
        node.mqtt.publish_ros_msg.assert_not_called()
        for tick in range(5):
            self.monotonic.return_value = 100.0 + tick * 0.5
            state = self.messages['RecordingState']()
            state.bag_name = 'bag_' + str(tick)
            node.subscriptions[rt.SUB.RECORDING_STATE](state)
        node.mqtt.publish_ros_msg.assert_not_called()
        node._publish_recording_state()
        node.mqtt.publish_ros_msg.assert_called_once_with(rt.MQTT.PUB.RECORDING_STATE, state)
        self.assertEqual(state.bag_name, 'bag_4')
        self.monotonic.return_value = 104.0
        node._publish_recording_state()
        node.mqtt.publish_ros_msg.assert_called_once()
        self.assertIsNone(node.recording_sample)
        # Recovery uses a new state; the expired one is never replayed.
        recovered = self.messages['RecordingState']()
        node.subscriptions[rt.SUB.RECORDING_STATE](recovered)
        node._publish_recording_state()
        self.assertEqual(node.mqtt.publish_ros_msg.call_count, 2)
        node.mqtt.publish_ros_msg.assert_called_with(rt.MQTT.PUB.RECORDING_STATE, recovered)

    def test_command_constructor_recording_ping_and_queue_handoff(self):
        node = self.command_node()
        self.assertEqual(node.process_rate_hz, 20.0)
        self.assertEqual([(period, callback.__name__) for period, callback in node.timers],
                         [(0.05, '_process_commands')])
        self.assertEqual(set(node.config), node.declared)
        self.assertEqual(set(node.clients), {
            Services.Shared.START_RECORDING, Services.Shared.STOP_RECORDING,
            Services.Shared.PING_MARK})
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
        client.connect_async.assert_called_once_with('broker.example.invalid', 8883, 60)
        client.loop_start.assert_called_once()
        transport._on_connect(client, None, None, NS(is_failure=False), None)
        self.assertEqual(client.subscribe.call_count, 3)
        transport._on_disconnect(client, None, None, None, None)
        self.assertFalse(transport.connected)
        transport._on_connect(client, None, None, NS(is_failure=False), None)
        self.assertEqual(client.subscribe.call_count, 6)

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
        sensors = constants('sensors')['Topics']
        recorder = constants('rosbag_manager')
        rt = Topics.TELEMETRY_GATEWAY_NODE
        self.assertEqual(rt.SUB.ULTRASONIC_LEFT, sensors.ULTRASONIC_LEFT_NODE.PUB.RANGE)
        self.assertEqual(rt.SUB.ULTRASONIC_RIGHT, sensors.ULTRASONIC_RIGHT_NODE.PUB.RANGE)
        self.assertEqual(rt.SUB.ATTITUDE, processing.IMU_NODE.PUB.IMU_AERO)
        self.assertEqual(rt.SUB.HEIGHT, processing.ULTRASONIC_FILTER_NODE.PUB.HEIGHT)
        self.assertEqual(rt.SUB.BATTERY, sensors.BATTERY_NODE.PUB.BATTERY_DATA)
        self.assertEqual(rt.SUB.GPS, sensors.GPS_NODE.PUB.GPS_DATA)
        self.assertEqual(rt.SUB.RECORDING_STATE,
                         recorder['Topics'].ROSBAG_MANAGER_NODE.PUB.RECORDING_STATE)
        for name in ('START_RECORDING', 'STOP_RECORDING'):
            self.assertEqual(getattr(Services.COMMAND_GATEWAY_NODE.SRV, name),
                             getattr(recorder['Services'].ROSBAG_MANAGER_NODE.SRV, name))


if __name__ == '__main__':
    unittest.main()
