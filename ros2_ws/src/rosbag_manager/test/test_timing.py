"""Exercise timer separation and lifecycle with simulated ROS and subprocesses."""

import ast
from datetime import datetime
import math
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


class RecordingTimingTests(unittest.TestCase):
    def setUp(self):
        self.params = {'process_check_rate_hz': 2.0, 'publish_rate_hz': 0.5}
        self.process = Mock()
        self.process.poll.return_value = None
        self.popen = Mock(return_value=self.process)
        self.makedirs = Mock()
        owner = self

        class FakeNode:
            def __init__(self, name):
                self.get_logger = Mock()
                self.create_publisher = Mock(return_value=Mock())
                self.create_service = Mock()
                self.create_timer = Mock()

            def declare_parameter(self, name, default):
                owner.params.setdefault(name, default)

            def get_parameter(self, name):
                return NS(value=owner.params[name])

            def destroy_node(self):
                pass

        path = Path(__file__).resolve().parents[1] / 'rosbag_manager/rosbag_manager_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        scope = dict(
            Node=FakeNode, math=math, os=NS(path=os.path, makedirs=self.makedirs),
            signal=signal, datetime=datetime, RecordingState=NS,
            StartRecording=object, StopRecording=object,
            subprocess=NS(Popen=self.popen, TimeoutExpired=subprocess.TimeoutExpired),
            Topics=NS(ROSBAG_MANAGER_NODE=NS(PUB=NS(RECORDING_STATE='/state'))),
            Services=NS(ROSBAG_MANAGER_NODE=NS(SRV=NS(
                START_RECORDING='/start', STOP_RECORDING='/stop'))),
        )
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['RosbagManagerNode']
        self.node = self.node_type()

    def start(self):
        return self.node.handle_start_recording(None, NS())

    def test_independent_timer_periods(self):
        calls = self.node.create_timer.call_args_list
        self.assertEqual([(c.args[0], c.args[1].__name__) for c in calls],
                         [(0.5, 'check_recorder'), (2.0, 'publish_state')])

    def test_invalid_rates_fail_before_creating_directories_or_timers(self):
        for name in ('process_check_rate_hz', 'publish_rate_hz'):
            original = self.params[name]
            for value in (0.0, -1.0, math.nan, math.inf):
                with self.subTest(name=name, value=value):
                    self.params[name] = value
                    self.makedirs.reset_mock()
                    with self.assertRaisesRegex(ValueError, name):
                        self.node_type()
                    self.makedirs.assert_not_called()
            self.params[name] = original

    def test_periodic_publication_never_polls_or_starts_recorder(self):
        self.node.recording = True
        self.node.rosbag_proc = self.process
        for _ in range(3):
            self.node.publish_state()
        self.assertEqual(self.node.state_pub.publish.call_count, 3)
        self.process.poll.assert_not_called()
        self.popen.assert_not_called()

    def test_unchanged_process_checks_do_not_publish(self):
        self.node.check_recorder()
        self.process.poll.assert_not_called()
        self.node.recording = True
        self.node.rosbag_proc = self.process
        for _ in range(3):
            self.node.check_recorder()
        self.assertEqual(self.process.poll.call_count, 3)
        self.node.state_pub.publish.assert_not_called()

    def test_unexpected_exit_publishes_once_without_waiting_for_state_timer(self):
        self.node.recording = True
        self.node.current_bag_name = 'failed_bag'
        self.node.rosbag_proc = self.process
        self.process.poll.return_value = 2
        self.node.check_recorder()
        self.node.check_recorder()
        self.node.state_pub.publish.assert_called_once()
        state = self.node.state_pub.publish.call_args.args[0]
        self.assertFalse(state.recording)
        self.assertEqual(state.bag_name, 'failed_bag')
        self.assertIn('code 2', state.last_error)
        self.assertIsNone(self.node.rosbag_proc)
        self.node.publish_state()
        self.assertEqual(self.node.state_pub.publish.call_count, 2)

    def test_start_preserves_recorder_command_and_publishes_immediately(self):
        response = self.start()
        self.assertTrue(response.success)
        self.assertEqual(response.effective_bag_name, self.node.current_bag_name)
        command = self.popen.call_args.args[0]
        self.assertEqual(command[:7], ['ros2', 'bag', 'record', '-a', '-s', 'mcap', '-o'])
        self.assertTrue(command[-1].endswith(response.effective_bag_name))
        self.assertTrue(self.popen.call_args.kwargs['start_new_session'])
        self.node.state_pub.publish.assert_called_once()
        self.assertTrue(self.node.state_pub.publish.call_args.args[0].recording)

    def test_immediate_start_exit_returns_failure_and_publishes_once(self):
        self.process.poll.return_value = 1
        response = self.start()
        self.assertFalse(response.success)
        self.assertEqual(response.effective_bag_name, '')
        self.assertIn('code 1', response.error_message)
        self.node.state_pub.publish.assert_called_once()
        self.assertFalse(self.node.state_pub.publish.call_args.args[0].recording)

    def test_start_exception_publishes_error(self):
        self.popen.side_effect = OSError('recorder unavailable')
        response = self.start()
        self.assertFalse(response.success)
        self.assertEqual(response.error_message, 'recorder unavailable')
        self.node.state_pub.publish.assert_called_once()

    def test_stop_returns_name_and_publishes_without_waiting_for_timer(self):
        bag_name = self.start().effective_bag_name
        self.node.state_pub.publish.reset_mock()
        response = self.node.handle_stop_recording(None, NS())
        self.assertTrue(response.success)
        self.assertEqual(response.last_bag_name, bag_name)
        self.process.send_signal.assert_called_once_with(signal.SIGINT)
        self.process.wait.assert_called_once_with(timeout=5.0)
        self.node.state_pub.publish.assert_called_once()
        state = self.node.state_pub.publish.call_args.args[0]
        self.assertFalse(state.recording)
        self.assertEqual(state.bag_name, '')

    def test_stop_timeout_still_kills_and_reaps_recorder(self):
        self.start()
        self.process.wait.side_effect = [subprocess.TimeoutExpired('recorder', 5.0), 0]
        response = self.node.handle_stop_recording(None, NS())
        self.assertTrue(response.success)
        self.process.kill.assert_called_once_with()
        self.assertEqual(self.process.wait.call_count, 2)

    def test_duplicate_start_does_not_launch_another_recorder(self):
        self.start()
        response = self.start()
        self.assertFalse(response.success)
        self.assertEqual(response.error_message, 'Already recording')
        self.popen.assert_called_once()


if __name__ == '__main__':
    unittest.main()
