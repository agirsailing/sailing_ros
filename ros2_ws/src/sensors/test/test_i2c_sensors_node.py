"""I2C scheduling, sample freshness and lifecycle with simulated drivers."""

import ast
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parent / 'sail_common'))
from sail_common.freshness import is_fresh


class Message:
    def __init__(self):
        self.header = NS(stamp=None, frame_id='')
        self.linear_acceleration = NS(x=0, y=0, z=0)
        self.angular_velocity = NS(x=0, y=0, z=0)
        self.vector = NS(x=0, y=0, z=0)
        self.orientation_covariance = [0.0] * 9


class I2CNodeTests(unittest.TestCase):
    def setUp(self):
        self.params = dict(bus=1, mux_address=0x70, mux_channel_count=4,
                           qos_depth=10, retry_interval_s=2.0)
        self.params.update({
            'compass.enabled': True, 'compass.channel': 0, 'compass.address': 0x0E,
            'compass.frame_id': 'compass', 'compass.read_rate_hz': 10.0,
            'compass.publish_rate_hz': 5.0, 'compass.max_sample_age_s': 0.5,
            'compass.reset_value': 1, 'compass.measurement_value': 1,
            'compass.reset_delay_s': 0.1, 'compass.conversion_delay_s': 0.02,
        })
        self.stamp = NS(sec=200, nanosec=0)
        self.monotonic = Mock(return_value=100.0)
        self.compass = Mock()
        self.compass.read.return_value = (100, -200, 300)
        self.compass_factory = Mock(return_value=self.compass)
        self.bus = Mock()
        self.bus_factory = Mock(return_value=self.bus)
        self.mux = Mock()
        self.mux_factory = Mock(return_value=self.mux)
        self.threads = NS(Thread=Mock(), Event=threading.Event, Lock=threading.Lock)
        owner = self

        class FakeNode:
            def __init__(self, name):
                self.get_logger = Mock()
                self.get_clock = lambda: NS(now=lambda: NS(
                    to_msg=lambda: owner.stamp,
                    nanoseconds=owner.stamp.sec * 1_000_000_000 + owner.stamp.nanosec))
                self.create_publisher = Mock(side_effect=lambda *args: Mock())
                self.create_timer = Mock()
                self.get_parameters = Mock()
                self.list_parameters = lambda *args, **kwargs: NS(names=[])
                self.destroyed = False

            def declare_parameter(self, name, kind):
                return NS(value=owner.params[name])

            def destroy_node(self):
                self.destroyed = True

        path = PACKAGE / 'sensors/i2c_sensors_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        scope = dict(
            Node=FakeNode, Parameter=NS(Type=NS(BOOL=1, STRING=2, INTEGER=3, DOUBLE=4)),
            Imu=Message, Vector3Stamped=Message, SMBus=self.bus_factory,
            I2CMultiplexer=self.mux_factory, CompassDriver=self.compass_factory,
            Topics=NS(I2C_SENSORS_NODE=NS(PUB=NS(IMU_DATA='/imu/data',
                                               COMPASS_DATA='/compass/data'))),
            threading=self.threads, time=NS(monotonic=self.monotonic),
            math=math, is_fresh=is_fresh,
        )
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['I2CSensorsNode']
        self.node = self.node_type()

    def test_read_rates_and_publish_rates_are_independent(self):
        calls = self.node.create_timer.call_args_list
        self.assertEqual([call.args[0] for call in calls], [0.2])
        workers = self.threads.Thread.call_args_list
        self.assertEqual([call.kwargs['args'][1] for call in workers], [10.0])
        self.node.publish_compass()
        self.compass_factory.assert_not_called()
        self.node.compass_pub.publish.assert_not_called()

    def test_read_does_not_publish_and_preserves_driver_contracts(self):
        self.node.read_compass()
        self.node.compass_pub.publish.assert_not_called()
        self.compass_factory.assert_called_once_with(self.mux, 0, 0x0E, 1, 1, 0.1, 0.02)
        self.node.publish_compass()
        compass = self.node.compass_pub.publish.call_args.args[0]
        self.assertEqual(compass.vector.y, -200.0)
        self.assertEqual(compass.header.frame_id, 'compass')

    def test_paused_ros_clock_still_expires_both_sensors(self):
        self.node.read_compass()
        self.monotonic.return_value = 100.501
        self.node.publish_compass()
        self.node.compass_pub.publish.assert_not_called()

    def test_ros_clock_jumps_reject_cached_samples(self):
        self.node.read_compass()
        for seconds in (199, 201):
            self.stamp = NS(sec=seconds, nanosec=0)
            self.node.publish_compass()
        self.node.compass_pub.publish.assert_not_called()

    def test_compass_failure_clears_cached_sample(self):
        self.node.read_compass()
        self.compass.read.side_effect = OSError('disconnected')
        self.node.read_compass()
        self.node.publish_compass()
        self.node.compass_pub.publish.assert_not_called()

    def test_disabled_sensors_do_not_start_readers_or_open_bus(self):
        self.params['compass.enabled'] = False
        self.bus_factory.reset_mock()
        self.threads.Thread.reset_mock()
        node = self.node_type()
        self.bus_factory.assert_not_called()
        self.threads.Thread.assert_not_called()
        node.create_timer.assert_not_called()
        node.destroy_node()
        self.assertTrue(node.destroyed)
        self.params['compass.enabled'] = True
        node = self.node_type()
        self.assertEqual(node.create_timer.call_count, 1)
        self.assertEqual(self.threads.Thread.call_count, 1)
        self.assertFalse(hasattr(node, 'imu_pub'))

    def test_mux_initialization_failure_closes_open_bus(self):
        self.mux_factory.side_effect = ValueError('setup failed')
        with self.assertRaisesRegex(ValueError, 'setup failed'):
            self.node_type()
        self.bus.close.assert_called_once()

    def test_read_loop_accounts_for_work_and_does_not_replay_missed_ticks(self):
        for duration, expected_wait in ((0.005, 0.015), (0.04, 0.0)):
            self.monotonic.side_effect = [100.0, 100.0 + duration]
            self.node._stop = Mock()
            self.node._stop.is_set.side_effect = [False, True]
            read = Mock()
            self.node._read_loop(read, 50.0)
            read.assert_called_once()
            self.assertAlmostEqual(self.node._stop.wait.call_args.args[0], expected_wait)

    def test_blocked_read_does_not_block_publishing_and_bus_closes_after_join(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()

        def blocking_read():
            entered.set()
            release.wait(2.0)
            finished.set()
            return (100, 200, 300)

        self.threads.Thread = threading.Thread
        self.compass.read.side_effect = blocking_read
        node = self.node_type()
        self.mux.close.side_effect = lambda: self.assertTrue(
            finished.is_set() and all(not worker.is_alive() for worker in node._workers))
        try:
            self.assertTrue(entered.wait(1.0))
            cached = Message()
            cached.header.stamp = self.stamp
            node._store_sample('compass', cached)
            node.publish_compass()
            node.compass_pub.publish.assert_called_once_with(cached)
        finally:
            release.set()
            node.destroy_node()
        self.mux.close.assert_called_once()
        self.assertTrue(node.destroyed)

    def test_nonpositive_and_nonfinite_timing_values_fail_before_open(self):
        for name in ('compass.read_rate_hz', 'compass.publish_rate_hz',
                     'compass.max_sample_age_s', 'retry_interval_s'):
            old = self.params[name]
            for value in (0.0, -1.0, math.nan, math.inf):
                with self.subTest(name=name, value=value):
                    self.params[name] = value
                    self.bus_factory.reset_mock()
                    with self.assertRaisesRegex(ValueError, name):
                        self.node_type()
                    self.bus_factory.assert_not_called()
            self.params[name] = old


if __name__ == '__main__':
    unittest.main()
