"""Real DDS service and map round trip; MQTT transport is replaced locally."""

import json
from pathlib import Path
import time
from unittest.mock import patch

import pytest

rclpy = pytest.importorskip('rclpy')


def test_ping_round_trip_and_late_map_subscriber():
    from communication_web.command_gateway_node import CommandGatewayNode
    from communication_web.telemetry_gateway_node import TelemetryGatewayNode
    from communication_web.generated.ros_endpoints import Topics
    from gps_msgs.msg import GPSFix
    from rclpy.executors import SingleThreadedExecutor
    from rosidl_runtime_py.convert import message_to_ordereddict
    from sail_msgs.msg import MapDataMsg, Mark

    config = Path(__file__).resolve().parents[1] / 'config/params.yaml'
    rclpy.init(args=['--ros-args', '--params-file', str(config)])
    executor = SingleThreadedExecutor()
    nodes = []
    try:
        with patch('communication_web.telemetry_gateway_node.MqttClientWrapper'):
            telemetry = TelemetryGatewayNode()
        nodes.append(telemetry)
        with patch('communication_web.command_gateway_node.MqttClientWrapper'):
            commands = CommandGatewayNode()
        nodes.append(commands)
        probe = rclpy.create_node('ping_mark_pipeline_test')
        nodes.append(probe)
        gps_pub = probe.create_publisher(GPSFix, '/gps/data', 10)
        maps = []
        probe.create_subscription(MapDataMsg, '/web/ros/map', maps.append, 10)
        for node in nodes:
            executor.add_node(node)

        def until(predicate):
            deadline = time.monotonic() + 6
            while not predicate() and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.01)
            assert predicate()

        until(lambda: gps_pub.get_subscription_count() == 1
              and commands.ping_client.service_is_ready()
              and telemetry.position_pub.get_subscription_count() == 1)
        fix = GPSFix()
        fix.header.stamp = probe.get_clock().now().to_msg()
        fix.header.frame_id = 'gps'
        fix.status.status = 0
        fix.latitude, fix.longitude, fix.speed = 59.123456789, 18.987654321, 1.0
        gps_pub.publish(fix)
        until(lambda: maps and maps[-1].fix_valid)
        mt = Topics.COMMAND_GATEWAY_NODE.MQTT
        payload = json.dumps(dict(requestId='first', type=Mark.COMMITTEE)).encode()
        commands._enqueue_command(mt.SUB.PING_MARK, payload, False)
        until(lambda: 'first' in commands.mark_rpc.completed)
        reply = commands.mark_rpc.completed['first'][1]
        assert reply['success'] and reply['mark']['lat'] == fix.latitude
        assert reply['mark']['header']['stamp'] == dict(
            sec=fix.header.stamp.sec, nanosec=fix.header.stamp.nanosec)
        until(lambda: maps[-1].marks)
        assert maps[-1].marks[0].type == Mark.COMMITTEE

        # Equivalent to reopening the page: a late consumer gets the course
        # through the periodic full snapshot, without requesting another ping.
        late_maps = []
        probe.create_subscription(MapDataMsg, '/web/ros/map', late_maps.append, 10)
        until(lambda: late_maps and late_maps[-1].marks)
        assert message_to_ordereddict(late_maps[-1])['marks'][0] == reply['mark']

        fix.header.stamp = probe.get_clock().now().to_msg()
        fix.latitude = 60.0
        gps_pub.publish(fix)
        until(lambda: maps[-1].latitude_deg == 60.0)
        # QoS duplicate returns the cached response, not the new boat position.
        commands._enqueue_command(mt.SUB.PING_MARK, payload, False)
        until(lambda: commands.commands.empty())
        assert telemetry.marks[Mark.COMMITTEE].lat == 59.123456789
        commands._enqueue_command(mt.SUB.PING_MARK, b'{"requestId":"replace","type":0}', False)
        until(lambda: 'replace' in commands.mark_rpc.completed)
        assert commands.mark_rpc.completed['replace'][1]['success']
        until(lambda: maps[-1].marks[0].lat == 60.0)
        assert len(maps[-1].marks) == 1

        until(lambda: not maps[-1].fix_valid)
        commands._enqueue_command(mt.SUB.PING_MARK, b'{"requestId":"stale","type":1}', False)
        until(lambda: 'stale' in commands.mark_rpc.completed)
        assert not commands.mark_rpc.completed['stale'][1]['success']
        assert len(telemetry.marks) == 1
        assert maps[-1].marks[0].lat == 60.0
    finally:
        executor.shutdown()
        for node in reversed(nodes):
            node.destroy_node()
        rclpy.shutdown()
