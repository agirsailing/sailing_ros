"""Verify stamped height publication and the unchanged web payload over DDS."""

import math
from pathlib import Path
import time
from unittest.mock import patch

import pytest

rclpy = pytest.importorskip('rclpy')
pytest.importorskip('marti_common_msgs.msg')


def test_periodic_height_reaches_gateway_and_expires_without_new_measurements():
    """Use real ROS nodes/messages and only replace the MQTT connection."""
    from communication_web.telemetry_gateway_node import TelemetryGatewayNode
    from data_elaboration.ultrasonic_filter_node import UltrasonicFilterNode
    from marti_common_msgs.msg import Float64Stamped
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.serialization import deserialize_message, serialize_message
    from sail_msgs.msg import DashboardDataMsg
    from sensor_msgs.msg import Imu, Range

    src = Path(__file__).resolve().parents[2]
    rclpy.init(args=[
        '--ros-args', '--params-file', str(src / 'data_elaboration/config/params.yaml'),
        '--params-file', str(src / 'communication_web/config/params.yaml')])
    executor = SingleThreadedExecutor()
    nodes = []
    try:
        height = UltrasonicFilterNode()
        nodes.append(height)
        assert height.publish_timer.timer_period_ns == 50_000_000
        with patch('communication_web.telemetry_gateway_node.MqttClientWrapper'):
            gateway = TelemetryGatewayNode()
        nodes.append(gateway)
        probe = rclpy.create_node('height_gateway_test')
        nodes.append(probe)
        outputs, dashboards = [], []
        probe.create_subscription(Float64Stamped, '/processed/boat_height', outputs.append, 10)
        probe.create_subscription(
            DashboardDataMsg, '/web/ros/dashboard', dashboards.append, 10)
        imu_pub = probe.create_publisher(Imu, '/processed/imu/data', 10)
        range_pub = probe.create_publisher(Range, '/ultrasonic/left', 10)
        for node in nodes:
            executor.add_node(node)

        def until(predicate):
            deadline = time.monotonic() + 5.0
            while not predicate() and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.005)
            assert predicate()

        until(lambda: height.height_pub.get_subscription_count() == 2
              and gateway.telemetry_pub.get_subscription_count() == 1
              and imu_pub.get_subscription_count() == 1
              and range_pub.get_subscription_count() == 2)
        imu = Imu()
        imu.header.stamp = probe.get_clock().now().to_msg()
        imu.header.frame_id = 'imu_link_flu'
        imu.orientation.w = 1.0
        imu_pub.publish(imu)
        until(lambda: height.attitudes)
        reading = Range()
        reading.header.stamp = imu.header.stamp
        reading.header.frame_id = 'ultrasonic_left'
        reading.range, reading.min_range, reading.max_range = 1.0, 0.03, 4.5
        range_pub.publish(reading)
        until(lambda: len(outputs) >= 2 and dashboards and dashboards[-1].height_valid)
        result = deserialize_message(serialize_message(outputs[-1]), Float64Stamped)
        assert result.header.stamp == reading.header.stamp
        assert result.header.frame_id == 'boat_waterline'
        assert math.isclose(result.value, math.cos(math.radians(1.0)))
        assert math.isclose(dashboards[-1].height_m, result.value)
        assert all(item.header.stamp == reading.header.stamp for item in outputs)
        until(lambda: height.latest_height is None and not dashboards[-1].height_valid)
        assert math.isnan(dashboards[-1].height_m)
    finally:
        executor.shutdown()
        for node in reversed(nodes):
            node.destroy_node()
        rclpy.shutdown()
