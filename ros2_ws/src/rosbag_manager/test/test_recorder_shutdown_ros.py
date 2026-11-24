"""Exercise real MCAP closure; run with ROS and this workspace sourced."""

import time

import pytest
import rclpy
from rclpy.node import Node
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from std_msgs.msg import String
from sail_msgs.srv import StartRecording, StopRecording
from rosbag_manager.rosbag_manager_node import RosbagManagerNode


@pytest.mark.parametrize('shutdown', [False, True])
def test_real_recorder_flushes_mcap(tmp_path, shutdown):
    rclpy.init(args=['--ros-args', '-p', f'record_dir:={tmp_path}'])
    manager = RosbagManagerNode()
    probe = Node('recorder_shutdown_probe')
    publisher = probe.create_publisher(String, '/shutdown_test', 10)
    try:
        response = manager.handle_start_recording(None, StartRecording.Response())
        assert response.success, response.error_message
        process = manager.rosbag_proc
        bag = tmp_path / response.effective_bag_name
        deadline = time.monotonic() + 8
        while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.05)
        assert publisher.get_subscription_count() > 0, 'Recorder did not discover test topic'
        for _ in range(10):
            publisher.publish(String(data='recorded before shutdown'))
            rclpy.spin_once(probe, timeout_sec=0.05)
        if shutdown:
            manager.destroy_node()
            manager = None
        else:
            response = manager.handle_stop_recording(None, StopRecording.Response())
            assert response.success, response.error_message
        assert process.poll() == 0
        assert (bag / 'metadata.yaml').is_file()
        reader = SequentialReader()
        reader.open(StorageOptions(uri=str(bag), storage_id='mcap'), ConverterOptions('', ''))
        found = False
        while reader.has_next():
            topic, _, _ = reader.read_next()
            found |= topic == '/shutdown_test'
        assert found, 'MCAP contains no test samples after shutdown'
    finally:
        if manager is not None:
            manager.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()
