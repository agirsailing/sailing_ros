"""Exercise the real GPS-to-gateway DDS path without hardware or a broker."""

import math
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

rclpy = pytest.importorskip('rclpy')
gps_msgs = pytest.importorskip('gps_msgs.msg')


def test_gpsfix_reaches_web_without_navigation_intermediary():
    """Preserve source time, independent IMU yaw, and invalid/stale behavior."""
    from communication_web.telemetry_gateway_node import TelemetryGatewayNode
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.serialization import deserialize_message, serialize_message
    from sail_msgs.msg import DashboardDataMsg, MapDataMsg
    from sensor_msgs.msg import Imu
    from sensors.gps_node import GPSNode

    src = Path(__file__).resolve().parents[2]
    rclpy.init(args=[
        '--ros-args', '--params-file', str(src / 'sensors/config/params.yaml'),
        '--params-file', str(src / 'communication_web/config/params.yaml')])
    executor = SingleThreadedExecutor()
    nodes = []
    packet = SimpleNamespace(identity='NAV-PVT', lat=59.3, lon=18.1,
                             hMSL=12000, gSpeed=1500, headMot=270.0, pDOP=1.25,
                             hAcc=500, vAcc=800, numSV=12, fixType=3, gnssFixOk=1)
    reader = Mock()
    reader.read.return_value = (b'', packet)
    try:
        with (
            patch('sensors.gps_node.Serial'),
            patch('sensors.gps_node.UBXReader', return_value=reader),
            patch.object(GPSNode, '_read_loop'),
        ):
            gps = GPSNode()
        nodes.append(gps)
        with patch('communication_web.telemetry_gateway_node.MqttClientWrapper'):
            gateway = TelemetryGatewayNode()
        nodes.append(gateway)
        probe = rclpy.create_node('gpsfix_gateway_test')
        nodes.append(probe)
        fixes, maps, dashboards = [], [], []
        probe.create_subscription(gps_msgs.GPSFix, '/gps/data', fixes.append, 10)
        probe.create_subscription(MapDataMsg, '/web/ros/map', maps.append, 10)
        probe.create_subscription(
            DashboardDataMsg, '/web/ros/dashboard', dashboards.append, 10)
        attitude_pub = probe.create_publisher(Imu, '/processed/imu/data/aero', 10)
        for node in nodes:
            executor.add_node(node)

        def until(predicate):
            deadline = time.monotonic() + 5.0
            while not predicate() and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.01)
            assert predicate()

        until(lambda: gps.gps_pub.get_subscription_count() == 2
              and gateway.position_pub.get_subscription_count() == 1
              and gateway.telemetry_pub.get_subscription_count() == 1
              and attitude_pub.get_subscription_count() == 1)
        gps._read_packet()
        attitude = Imu()
        attitude.header.stamp = probe.get_clock().now().to_msg()
        attitude.orientation.z = math.sin(math.radians(75) / 2)
        attitude.orientation.w = math.cos(math.radians(75) / 2)
        attitude_pub.publish(attitude)
        until(lambda: fixes and maps and maps[-1].fix_valid
              and dashboards and dashboards[-1].attitude_valid)
        fix = deserialize_message(serialize_message(fixes[-1]), gps_msgs.GPSFix)
        assert fix.status.status == gps_msgs.GPSStatus.STATUS_FIX
        assert fix.speed == 1.5 and fix.track == 270.0
        assert fix.status.header == fix.header
        assert math.isnan(fix.err_horz)
        assert maps[-1].latitude_deg == 59.3 and maps[-1].longitude_deg == 18.1
        assert maps[-1].sog_mps == 1.5 and maps[-1].gps_stamp == fix.header.stamp
        assert math.isclose(dashboards[-1].yaw_deg, 75.0)  # Never replaced by GPS course.
        assert dashboards[-1].sog_valid and dashboards[-1].sog_mps == 1.5

        packet.gnssFixOk = 0
        gps._read_packet()
        invalid_stamp = gps._latest_sample[1]
        until(lambda: maps[-1].gps_stamp == invalid_stamp)
        until(lambda: not dashboards[-1].sog_valid)
        assert not maps[-1].fix_valid
        assert math.isnan(maps[-1].latitude_deg) and math.isnan(maps[-1].sog_mps)

        packet.gnssFixOk = 1
        gps._read_packet()
        recovery_stamp = gps._latest_sample[1]
        until(lambda: maps[-1].gps_stamp == recovery_stamp and maps[-1].fix_valid)
        # Timer repeats must expire without renewing the source timestamp.
        until(lambda: not maps[-1].fix_valid and not dashboards[-1].sog_valid)
        assert maps[-1].gps_stamp == recovery_stamp
        assert math.isnan(maps[-1].latitude_deg)
    finally:
        executor.shutdown()
        for node in reversed(nodes):
            node.destroy_node()
        rclpy.shutdown()
