"""Ultrasound timing, freshness and reader lifecycle without ROS or hardware."""

import ast
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'sail_common'))
from sail_common.freshness import is_fresh


class RangeMessage:
    ULTRASOUND = 0

    def __init__(self):
        self.header = NS(stamp=None, frame_id='')


class UltrasonicNodeTests(unittest.TestCase):
    def setUp(self):
        self.params = dict(
            enabled=True, endpoint_group='ULTRASONIC_LEFT_NODE', port='test',
            baudrate=9600, timeout_s=0.1, read_rate_hz=0.0, publish_rate_hz=20.0,
            max_sample_age_s=0.5, frame_id='ultrasonic_left', min_range_m=0.03,
            max_range_m=4.5, field_of_view_rad=0.1, qos_depth=10,
        )
        self.clock = Mock(return_value=100.0)
        self.stamp = NS(sec=200, nanosec=0)
        self.sensor = Mock(STA_OK=0, STA_ERR_DATA=5, last_operate_status=0)
        self.sensor.getDistance.return_value = 1000
        self.driver = Mock(return_value=self.sensor)
        self.threads = NS(Thread=Mock(), Event=threading.Event, Lock=threading.Lock)
        owner = self

        class FakeNode:
            def __init__(self, name):
                self.get_logger = Mock()
                self.get_clock = lambda: NS(now=lambda: NS(
                    to_msg=lambda: owner.stamp,
                    nanoseconds=owner.stamp.sec * 1_000_000_000 + owner.stamp.nanosec))
                self.create_publisher = Mock()
                self.create_timer = Mock()
                self.get_parameters = Mock()
                self.list_parameters = lambda *args, **kwargs: NS(names=[])
                self.destroyed = False

            def declare_parameter(self, name, kind):
                return NS(value=owner.params[name])

            def destroy_node(self):
                self.destroyed = True

        path = Path(__file__).resolve().parents[1] / 'sensors/ultrasonic_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        scope = dict(
            Node=FakeNode, Parameter=NS(Type=NS(BOOL=1, STRING=2, INTEGER=3, DOUBLE=4)),
            Range=RangeMessage, DFRobot_A02_Distance=self.driver,
            Topics=NS(ULTRASONIC_LEFT_NODE=NS(PUB=NS(RANGE='/ultrasonic/left')),
                      ULTRASONIC_RIGHT_NODE=NS(PUB=NS(RANGE='/ultrasonic/right'))),
            math=math, time=NS(monotonic=self.clock), threading=self.threads,
            is_fresh=is_fresh,
        )
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['UltrasonicNode']
        self.node = self.node_type()

    def test_independent_publication_timer_and_no_output_before_first_sample(self):
        self.node.create_timer.assert_called_once_with(0.05, self.node.publish_distance)
        self.node.publish_distance()
        self.node.range_pub.publish.assert_not_called()
        self.sensor.getDistance.assert_not_called()

    def test_publish_repeats_latest_with_original_timestamp_then_expires(self):
        self.node._read_distance(wait_for_data=True)
        self.clock.return_value = 100.1
        self.node.publish_distance()
        first = self.node.range_pub.publish.call_args.args[0]
        self.stamp = NS(sec=200, nanosec=100_000_000)
        self.node.publish_distance()
        repeated = self.node.range_pub.publish.call_args.args[0]
        self.assertIs(first.header.stamp, repeated.header.stamp)
        self.assertEqual(repeated.header.stamp.sec, 200)
        self.assertEqual(repeated.range, 1.0)
        self.assertEqual(repeated.header.frame_id, 'ultrasonic_left')
        self.assertEqual(repeated.min_range, 0.03)
        self.assertEqual(repeated.max_range, 4.5)
        self.sensor.getDistance.assert_called_once_with(wait_for_data=True)

        self.clock.return_value = 100.501
        self.node.publish_distance()
        self.assertEqual(self.node.range_pub.publish.call_count, 2)
        self.stamp = NS(sec=201, nanosec=0)
        self.node._read_distance(wait_for_data=True)  # Same number, new measurement.
        self.node.publish_distance()
        self.assertEqual(self.node.range_pub.publish.call_args.args[0].header.stamp.sec, 201)

    def test_idle_or_partial_reads_do_not_refresh_sample_age(self):
        self.node._read_distance(wait_for_data=True)
        self.sensor.getDistance.return_value = None
        self.sensor.last_operate_status = self.sensor.STA_ERR_DATA
        self.clock.return_value = 100.6
        self.node._read_distance(wait_for_data=True)
        self.node.publish_distance()
        self.node.range_pub.publish.assert_not_called()

    def test_ros_clock_jump_rejects_old_or_future_sample(self):
        self.node._read_distance(wait_for_data=True)
        for seconds in (199, 201):
            self.stamp = NS(sec=seconds, nanosec=0)
            self.node.publish_distance()
            self.node.range_pub.publish.assert_not_called()

    def test_paused_ros_clock_does_not_keep_sample_fresh(self):
        self.node._read_distance(wait_for_data=True)
        self.clock.return_value = 101.0
        self.node.publish_distance()
        self.node.range_pub.publish.assert_not_called()

    def test_newest_sample_wins_without_replaying_backlog(self):
        for value in (1000, 1200, 1500):
            self.sensor.getDistance.return_value = value
            self.node._read_distance(wait_for_data=True)
        self.node.publish_distance()
        self.node.range_pub.publish.assert_called_once()
        self.assertEqual(self.node.range_pub.publish.call_args.args[0].range, 1.5)

    def test_invalid_sample_or_serial_failure_clears_cached_value(self):
        for failure in ('invalid', 'disconnected'):
            with self.subTest(failure=failure):
                self.sensor.last_operate_status = 0
                self.sensor.getDistance.side_effect = None
                self.node._read_distance(wait_for_data=True)
                if failure == 'invalid':
                    self.sensor.last_operate_status = 3
                else:
                    self.sensor.getDistance.side_effect = OSError('disconnected')
                success = self.node._read_distance(wait_for_data=True)
                self.assertEqual(success, failure != 'disconnected')
                self.node.publish_distance()
                self.node.range_pub.publish.assert_not_called()

    def test_reader_mode_period_and_error_backoff(self):
        for rate, success, wait_for_data, delay in (
            (0.0, True, True, 0.0), (10.0, True, False, 0.1),
            (0.0, False, True, 0.1), (20.0, False, False, 0.1),
        ):
            with self.subTest(rate=rate, success=success):
                self.node.read_rate_hz = rate
                self.node._stop = Mock()
                self.node._stop.is_set.side_effect = [False, True]
                self.node._read_distance = Mock(return_value=success)
                self.node._read_loop()
                self.node._read_distance.assert_called_once_with(wait_for_data=wait_for_data)
                self.node._stop.wait.assert_called_once_with(delay)

    def test_disabled_node_opens_no_device_and_starts_no_worker(self):
        self.params['enabled'] = False
        self.driver.reset_mock()
        self.threads.Thread.reset_mock()
        node = self.node_type()
        self.driver.assert_not_called()
        self.threads.Thread.assert_not_called()
        node.create_timer.assert_not_called()
        node.destroy_node()
        self.assertTrue(node.destroyed)

    def test_failed_setup_closes_open_port(self):
        self.sensor.set_dis_range.side_effect = ValueError('setup failure')
        with self.assertRaisesRegex(ValueError, 'setup failure'):
            self.node_type()
        self.sensor.close.assert_called_once()

    def test_shutdown_joins_reader_before_closing_port(self):
        entered = threading.Event()
        finished = threading.Event()

        def read(wait_for_data):
            entered.set()
            # Simulate a finite blocking serial timeout.
            threading.Event().wait(0.02)
            finished.set()
            return None

        self.sensor.last_operate_status = self.sensor.STA_ERR_DATA
        self.sensor.getDistance.side_effect = read
        self.sensor.close.side_effect = lambda: self.assertTrue(finished.is_set())
        self.threads.Thread = threading.Thread
        node = self.node_type()
        try:
            self.assertTrue(entered.wait(1.0))
        finally:
            node.destroy_node()
        self.assertFalse(node._reader.is_alive())
        self.sensor.close.assert_called_once()
        self.assertTrue(node.destroyed)

    def test_bad_rates_and_nonfinite_timeout_are_rejected(self):
        for name, value in (
            ('read_rate_hz', -1.0), ('read_rate_hz', math.nan),
            ('publish_rate_hz', 0.0), ('publish_rate_hz', math.inf),
            ('max_sample_age_s', 0.0), ('timeout_s', math.inf),
        ):
            with self.subTest(name=name, value=value):
                old = self.params[name]
                self.params[name] = value
                with self.assertRaisesRegex(ValueError, name):
                    self.node_type()
                self.params[name] = old


if __name__ == '__main__':
    unittest.main()
