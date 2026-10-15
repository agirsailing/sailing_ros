"""Battery acquisition and shutdown policy with simulated GPIO and subprocesses."""

import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


class BatteryMessage:
    def __init__(self):
        self.header = NS(stamp=None, frame_id='')
        self.voltage_v = 0.0
        self.low = False


class BatteryNodeTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'sensors/battery_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        self.gpio = Mock()
        self.gpio.gpio_read.return_value = 0
        self.process = Mock()
        self.process.run.return_value.returncode = 0
        scope = dict(Node=object, lgpio=self.gpio, math=math,
                     time=NS(monotonic=lambda: 100), BatteryData=BatteryMessage,
                     subprocess=self.process)
        # Load the actual timeout constant and class, without importing hardware/ROS.
        timeout = next(item for item in tree.body if isinstance(item, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'VOLTAGE_TIMEOUT_S'
                               for target in item.targets))
        exec(compile(ast.Module(body=[timeout, definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node = object.__new__(scope['BatteryNode'])
        self.node.chip, self.node.gpio_line, self.node.active_level = 0, 13, 1
        self.node.link = NS(latest=(12.4, 99))
        self.node.battery_pub = Mock()
        self.node.get_logger = Mock()
        self.node.get_clock = lambda: NS(now=lambda: NS(to_msg=lambda: NS(sec=200, nanosec=123)))
        self.node.low_samples = 0
        self.node.low_samples_required = 1
        self.node.shutdown_requested = False
        self.node.shutdown_enabled = False
        self.node.shutdown_command = ['simulated-shutdown']

    def test_snapshot_has_ros_timestamp_voltage_and_alarm_polarity(self):
        for active, level in ((1, 1), (1, 0), (0, 0), (0, 1)):
            with self.subTest(active=active, level=level):
                self.node.active_level = active
                self.gpio.gpio_read.return_value = level
                self.node.publish_battery()
                msg = self.node.battery_pub.publish.call_args.args[0]
                self.assertEqual((msg.header.stamp.sec, msg.header.stamp.nanosec), (200, 123))
                self.assertEqual(msg.header.frame_id, '')
                self.assertEqual(msg.voltage_v, 12.4)
                self.assertEqual(msg.low, active == level)

    def test_missing_or_old_voltage_still_publishes_the_low_alarm(self):
        self.gpio.gpio_read.return_value = 1
        for latest in (None, (12.4, 94.9), (12.4, 101)):
            with self.subTest(latest=latest):
                self.node.link.latest = latest
                self.node.publish_battery()
                msg = self.node.battery_pub.publish.call_args.args[0]
                self.assertTrue(math.isnan(msg.voltage_v))
                self.assertTrue(msg.low)

    def test_gpio_failure_never_publishes_a_false_healthy_sample_and_recovers(self):
        for result in (-1, 2, OSError('disconnected')):
            with self.subTest(result=result):
                self.gpio.gpio_read.side_effect = [result]
                self.node.publish_battery()
                self.node.battery_pub.publish.assert_not_called()
                self.process.run.assert_not_called()
        self.gpio.gpio_read.side_effect = None
        self.gpio.gpio_read.return_value = 1
        self.node.publish_battery()
        self.assertTrue(self.node.battery_pub.publish.call_args.args[0].low)

    def test_shutdown_requires_consecutive_samples_and_preserves_raw_alarm(self):
        self.node.shutdown_enabled = True
        self.node.low_samples_required = 2
        for level in (1, 0, 1):
            self.gpio.gpio_read.return_value = level
            self.node.publish_battery()
            self.assertEqual(self.node.battery_pub.publish.call_args.args[0].low, bool(level))
            self.process.run.assert_not_called()
        self.gpio.gpio_read.return_value = 1
        self.node.publish_battery()
        self.process.run.assert_called_once_with(['simulated-shutdown'], check=False)

    def test_shutdown_is_requested_once_after_publishing_even_without_voltage(self):
        self.node.shutdown_enabled = True
        self.node.link.latest = None
        self.gpio.gpio_read.return_value = 1
        self.process.run.side_effect = lambda *args, **kwargs: (
            self.assertEqual(self.node.battery_pub.publish.call_count, 1) or NS(returncode=0))
        for _ in range(3):
            self.node.publish_battery()
        self.process.run.assert_called_once_with(['simulated-shutdown'], check=False)
        self.assertEqual(self.node.battery_pub.publish.call_count, 3)

    def test_disabled_shutdown_keeps_publishing_and_never_executes_command(self):
        self.gpio.gpio_read.return_value = 1
        for _ in range(3):
            self.node.publish_battery()
        self.process.run.assert_not_called()
        self.assertEqual(self.node.battery_pub.publish.call_count, 3)
        self.node.get_logger().warning.assert_called_once()

    def test_failed_shutdown_is_logged_without_retrying_each_sample(self):
        self.node.shutdown_enabled = True
        self.gpio.gpio_read.return_value = 1
        for failure in (NS(returncode=2), OSError('command unavailable')):
            with self.subTest(failure=failure):
                self.node.shutdown_requested = False
                self.process.run.reset_mock()
                self.node.get_logger().error.reset_mock()
                self.process.run.side_effect = [failure]
                self.node.publish_battery()
                self.node.publish_battery()
                self.process.run.assert_called_once()
                self.node.get_logger().error.assert_called_once()

    def test_shutdown_configuration_validation(self):
        self.node.get_parameters = Mock()
        self.node.list_parameters = lambda *args, **kwargs: NS(names=[])
        self.node.pull, self.node.rate_hz, self.node.qos_depth = 'down', 10.0, 10
        self.node._validate_parameters()
        self.node.low_samples_required = 0
        with self.assertRaisesRegex(ValueError, 'low_samples_required'):
            self.node._validate_parameters()
        self.node.low_samples_required = 1
        self.node.shutdown_command = []
        with self.assertRaisesRegex(ValueError, 'shutdown_command'):
            self.node._validate_parameters()

    def test_replay_disables_shutdown_after_loading_the_shared_parameters(self):
        launch_dir = Path(__file__).resolve().parents[1] / 'launch'
        for filename in ('live_sensors.launch.py', 'sensors_launch.py', 'replay_sensors.launch.py'):
            with self.subTest(filename=filename):
                tree = ast.parse((launch_dir / filename).read_text(encoding='utf-8'))
                function = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                                and item.name == 'generate_launch_description')
                scope = dict(LaunchDescription=list, Node=lambda **kwargs: NS(**kwargs),
                             DeclareLaunchArgument=lambda *args, **kwargs: None,
                             LaunchConfiguration=lambda name: name,
                             FindPackageShare=lambda name: name,
                             PathJoinSubstitution=lambda parts: '/'.join(parts))
                exec(compile(ast.Module(body=[function], type_ignores=[]), filename, 'exec'), scope)
                nodes = scope['generate_launch_description']()
                battery = [node for node in nodes if getattr(node, 'name', '') == 'battery_node']
                self.assertEqual(len(battery), 1)
                params = battery[0].parameters
                self.assertEqual(params[0], 'sensors_params_file')
                if filename == 'replay_sensors.launch.py':
                    self.assertEqual(params[-1], {'shutdown_enabled': False})
                else:
                    self.assertEqual(params, ['sensors_params_file'])


if __name__ == '__main__':
    unittest.main()
