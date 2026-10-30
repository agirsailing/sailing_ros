"""Battery acquisition and shutdown policy with simulated GPIO and subprocesses."""

import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parent / 'sail_common'))
from sail_common.freshness import is_fresh


class BatteryMessage:
    def __init__(self):
        self.header = NS(stamp=None, frame_id='')
        self.voltage_v = 0.0
        self.low = False


class BatteryNodeTests(unittest.TestCase):
    def setUp(self):
        path = PACKAGE / 'sensors/battery_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        self.gpio = Mock()
        self.gpio.gpio_read.return_value = 0
        self.process = Mock()
        self.process.run.return_value.returncode = 0
        self.params = dict(gpio_chip=0, gpio_line=13, link_gpio_line=6,
                           active_level=1, pull='down', read_rate_hz=10.0,
                           publish_rate_hz=10.0, max_sample_age_s=0.5,
                           voltage_max_age_s=5.0, qos_depth=10,
                           shutdown_enabled=False, low_samples_required=1,
                           shutdown_command=['simulated-shutdown'])
        self.stamp = NS(sec=200, nanosec=123)
        self.monotonic = Mock(return_value=100.0)
        self.link = NS(latest=(12.4, 99), close=Mock())
        self.driver_factory = Mock(return_value=self.link)
        owner = self

        class FakeNode:
            def __init__(self, name):
                self.get_logger = Mock()
                self.get_clock = lambda: NS(now=lambda: NS(
                    to_msg=lambda: owner.stamp,
                    nanoseconds=owner.stamp.sec * 1_000_000_000 + owner.stamp.nanosec))
                self.create_publisher = Mock(return_value=Mock())
                self.create_timer = Mock()
                self.get_parameters = Mock()
                self.list_parameters = lambda *args, **kwargs: NS(names=[])

            def declare_parameter(self, name, kind):
                return NS(value=owner.params[name])

            def destroy_node(self):
                pass

        scope = dict(Node=FakeNode, lgpio=self.gpio, math=math,
                     time=NS(monotonic=self.monotonic), BatteryData=BatteryMessage,
                     subprocess=self.process, is_fresh=is_fresh,
                     BatteryDriver=self.driver_factory,
                     Parameter=NS(Type=NS(INTEGER=1, DOUBLE=2, STRING=3, BOOL=4,
                                          STRING_ARRAY=5)),
                     Topics=NS(BATTERY_NODE=NS(PUB=NS(BATTERY_DATA='/battery/data'))))
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['BatteryNode']
        self.node = self.node_type()

    def read_and_publish(self):
        self.node.read_battery()
        self.node.publish_battery()

    def test_snapshot_has_ros_timestamp_voltage_and_alarm_polarity(self):
        for active, level in ((1, 1), (1, 0), (0, 0), (0, 1)):
            with self.subTest(active=active, level=level):
                self.node.active_level = active
                self.gpio.gpio_read.return_value = level
                self.read_and_publish()
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
                self.read_and_publish()
                msg = self.node.battery_pub.publish.call_args.args[0]
                self.assertTrue(math.isnan(msg.voltage_v))
                self.assertTrue(msg.low)

    def test_gpio_failure_never_publishes_a_false_healthy_sample_and_recovers(self):
        for result in (-1, 2, OSError('disconnected')):
            with self.subTest(result=result):
                self.node.read_battery()  # An older good sample must be cleared.
                self.gpio.gpio_read.side_effect = [result]
                self.read_and_publish()
                self.node.battery_pub.publish.assert_not_called()
                self.process.run.assert_not_called()
                self.gpio.gpio_read.side_effect = None
        self.gpio.gpio_read.side_effect = None
        self.gpio.gpio_read.return_value = 1
        self.read_and_publish()
        self.assertTrue(self.node.battery_pub.publish.call_args.args[0].low)

    def test_shutdown_requires_consecutive_samples_and_preserves_raw_alarm(self):
        self.node.shutdown_enabled = True
        self.node.low_samples_required = 2
        for level in (1, 0, 1):
            self.gpio.gpio_read.return_value = level
            self.read_and_publish()
            self.assertEqual(self.node.battery_pub.publish.call_args.args[0].low, bool(level))
            self.process.run.assert_not_called()
        self.gpio.gpio_read.return_value = 1
        self.read_and_publish()
        self.process.run.assert_called_once_with(['simulated-shutdown'], check=False)

    def test_shutdown_does_not_wait_for_publication_or_voltage(self):
        self.node.shutdown_enabled = True
        self.node.link.latest = None
        self.gpio.gpio_read.return_value = 1
        for _ in range(3):
            self.node.read_battery()
        self.process.run.assert_called_once_with(['simulated-shutdown'], check=False)
        self.node.battery_pub.publish.assert_not_called()
        self.node.publish_battery()
        self.assertTrue(self.node.battery_pub.publish.call_args.args[0].low)

    def test_disabled_shutdown_keeps_publishing_and_never_executes_command(self):
        self.gpio.gpio_read.return_value = 1
        for _ in range(3):
            self.read_and_publish()
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
                self.read_and_publish()
                self.read_and_publish()
                self.process.run.assert_called_once()
                self.node.get_logger().error.assert_called_once()

    def test_shutdown_configuration_validation(self):
        self.node.get_parameters = Mock()
        self.node.list_parameters = lambda *args, **kwargs: NS(names=[])
        self.node._validate_parameters()
        self.node.low_samples_required = 0
        with self.assertRaisesRegex(ValueError, 'low_samples_required'):
            self.node._validate_parameters()
        self.node.low_samples_required = 1
        self.node.shutdown_command = []
        with self.assertRaisesRegex(ValueError, 'shutdown_command'):
            self.node._validate_parameters()

    def test_rates_and_age_limits_reject_zero_negative_and_non_finite(self):
        for name in ('read_rate_hz', 'publish_rate_hz',
                     'max_sample_age_s', 'voltage_max_age_s'):
            original = self.params[name]
            for value in (0.0, -1.0, math.nan, math.inf):
                with self.subTest(name=name, value=value):
                    self.params[name] = value
                    self.gpio.gpiochip_open.reset_mock()
                    with self.assertRaisesRegex(ValueError, name):
                        self.node_type()
                    self.gpio.gpiochip_open.assert_not_called()
            self.params[name] = original

    def test_independent_timers_and_no_publication_before_first_read(self):
        self.params['publish_rate_hz'] = 2.0
        node = self.node_type()
        calls = node.create_timer.call_args_list
        self.assertEqual([(c.args[0], c.args[1].__name__) for c in calls],
                         [(0.1, 'read_battery'), (0.5, 'publish_battery')])
        node.publish_battery()
        node.battery_pub.publish.assert_not_called()
        self.gpio.gpio_read.assert_not_called()
        node.read_battery()
        node.battery_pub.publish.assert_not_called()
        for _ in range(3):
            node.publish_battery()
        self.gpio.gpio_read.assert_called_once()
        self.assertEqual(node.battery_pub.publish.call_count, 3)

    def test_republication_preserves_stamp_and_does_not_confirm_shutdown(self):
        self.node.shutdown_enabled = True
        self.node.low_samples_required = 2
        self.gpio.gpio_read.return_value = 1
        self.node.read_battery()
        for nanos in (100_000_000, 200_000_000, 300_000_000):
            self.stamp = NS(sec=200, nanosec=nanos)
            self.node.publish_battery()
            msg = self.node.battery_pub.publish.call_args.args[0]
            self.assertEqual((msg.header.stamp.sec, msg.header.stamp.nanosec), (200, 123))
        self.assertEqual(self.node.low_samples, 1)
        self.process.run.assert_not_called()
        self.node.read_battery()
        self.process.run.assert_called_once()

    def test_alarm_expiry_checks_ros_and_monotonic_clocks_separately(self):
        for ros_stamp, monotonic in ((NS(sec=201, nanosec=0), 100.0),
                                     (NS(sec=200, nanosec=123), 100.6),
                                     (NS(sec=199, nanosec=0), 100.0)):
            with self.subTest(ros_stamp=ros_stamp, monotonic=monotonic):
                self.stamp = NS(sec=200, nanosec=123)
                self.monotonic.return_value = 100.0
                self.node.read_battery()
                self.stamp = ros_stamp
                self.monotonic.return_value = monotonic
                self.node.publish_battery()
                self.node.battery_pub.publish.assert_not_called()

    def test_voltage_expires_between_read_and_publish_without_expiring_alarm(self):
        self.node.voltage_max_age_s = 1.0
        self.node.read_battery()
        self.node.publish_battery()
        self.assertEqual(self.node.battery_pub.publish.call_args.args[0].voltage_v, 12.4)
        self.monotonic.return_value = 100.2
        self.node.publish_battery()
        self.assertTrue(math.isnan(self.node.battery_pub.publish.call_args.args[0].voltage_v))
        # A new alarm timestamp must not refresh the old voltage's age.
        self.node.read_battery()
        self.node.publish_battery()
        self.assertTrue(math.isnan(self.node.battery_pub.publish.call_args.args[0].voltage_v))
        self.link.latest = (12.6, 100.2)
        self.node.read_battery()
        self.node.publish_battery()
        self.assertEqual(self.node.battery_pub.publish.call_args.args[0].voltage_v, 12.6)

    def test_alarm_age_boundary_and_recovery(self):
        self.node.read_battery()
        self.monotonic.return_value = 100.5
        self.node.publish_battery()
        self.node.battery_pub.publish.assert_called_once()
        self.monotonic.return_value = 100.50001
        self.node.publish_battery()
        self.node.battery_pub.publish.assert_called_once()
        self.node.read_battery()
        self.node.publish_battery()
        self.assertEqual(self.node.battery_pub.publish.call_count, 2)

    def test_replay_starts_no_hardware_while_live_loads_battery_parameters(self):
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
                if filename == 'replay_sensors.launch.py':
                    self.assertEqual(nodes, [])
                    continue
                battery = [node for node in nodes if getattr(node, 'name', '') == 'battery_node']
                self.assertEqual(len(battery), 1)
                params = battery[0].parameters
                self.assertEqual(params[0], 'sensors_params_file')
                self.assertEqual(params, ['sensors_params_file'])


if __name__ == '__main__':
    unittest.main()
