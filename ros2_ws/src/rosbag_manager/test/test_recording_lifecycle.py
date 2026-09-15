"""Check recording state and service responses without starting a recorder."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rosbag_manager.rosbag_manager_node import RosbagManagerNode


def make_node():
    """Build only the state needed by callbacks, without initializing ROS."""
    node = object.__new__(RosbagManagerNode)
    node.recording = False
    node.current_bag_name = ''
    node.last_error = ''
    node.rosbag_proc = None
    node.record_dir = '/unused-test-output'
    node.bag_prefix = 'test_'
    node.sigint_timeout = 5.0
    node.state_pub = Mock()
    node.get_logger = Mock(return_value=Mock())
    return node


def test_start_returns_effective_bag_name():
    """Return the name of the directory passed to the recorder."""
    node = make_node()
    process = Mock()
    process.poll.return_value = None
    with patch('rosbag_manager.rosbag_manager_node.subprocess.Popen',
               return_value=process) as popen:
        response = node.handle_start_recording(None, SimpleNamespace())
    assert response.success
    assert response.effective_bag_name == node.current_bag_name
    assert response.effective_bag_name.startswith('test_')
    assert popen.call_args.args[0][-1].endswith(response.effective_bag_name)


def test_start_reports_immediate_process_failure():
    """Do not report a successful start when the child has already exited."""
    node = make_node()
    process = Mock()
    process.poll.return_value = 1
    with patch('rosbag_manager.rosbag_manager_node.subprocess.Popen',
               return_value=process):
        response = node.handle_start_recording(None, SimpleNamespace())
    assert not response.success
    assert response.effective_bag_name == ''
    assert 'code 1' in response.error_message
    assert not node.recording


def test_state_detects_unexpected_exit():
    """Update the published state when a previously running recorder exits."""
    node = make_node()
    node.recording = True
    node.rosbag_proc = Mock()
    node.rosbag_proc.poll.return_value = 2
    node.publish_state()
    assert not node.recording
    assert node.rosbag_proc is None
    state = node.state_pub.publish.call_args.args[0]
    assert not state.recording
    assert 'code 2' in state.last_error


def test_stop_returns_bag_name_before_clearing_state():
    """Preserve the completed bag name in the service response."""
    node = make_node()
    node.recording = True
    node.current_bag_name = 'completed_bag'
    process = Mock()
    node.rosbag_proc = process
    response = node.handle_stop_recording(None, SimpleNamespace())
    assert response.success
    assert response.last_bag_name == 'completed_bag'
    assert node.current_bag_name == ''
    assert not node.recording
    process.wait.assert_called_once_with(timeout=5.0)


def test_stop_reaps_process_after_timeout():
    """Wait for the killed child so it is not left behind."""
    node = make_node()
    node.recording = True
    process = Mock()
    process.wait.side_effect = [subprocess.TimeoutExpired('recorder', 5.0), 0]
    node.rosbag_proc = process
    response = node.handle_stop_recording(None, SimpleNamespace())
    assert response.success
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
