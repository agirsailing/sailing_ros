"""BNO085 reader/publication scheduling and expiry with simulated hardware."""

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
        self.orientation = NS(x=0, y=0, z=0, w=0)
        self.linear_acceleration = NS(x=0, y=0, z=0)
        self.angular_velocity = NS(x=0, y=0, z=0)
        self.magnetic_field = NS(x=0, y=0, z=0)


class ImuSensorTests(unittest.TestCase):
    def setUp(self):
        self.params = dict(port='/dev/ttyAMA0', baudrate=3000000, frame_id='imu',
                           read_rate_hz=0.0, publish_rate_hz=50.0, max_sample_age_s=0.5,
                           timeout_s=0.1, report_rate_hz=100.0, magnetometer_rate_hz=50.0,
                           orientation_report='rotation_vector', roll_pitch_variance_rad2=0.0,
                           reset_delay_s=0.5, stale_timeout_s=1.0, retry_interval_s=2.0, qos_depth=10)
        self.stamp = NS(sec=200, nanosec=0)
        self.monotonic = Mock(return_value=100.0)
        self.sample = NS(orientation=(0, 0, 0, 2), orientation_accuracy=3,
                         heading_accuracy_rad=0.1, acceleration=(1, 2, 9.8),
                         angular_velocity=(0.1, 0.2, 0.3), magnetic_field=(1e-5, 2e-5, 3e-5),
                         received_at=100.0, oldest_received_at=100.0, magnetic_received_at=100.0)
        self.driver = Mock()
        self.driver.read.return_value = self.sample
        self.factory = Mock(return_value=self.driver)
        self.transport = Mock()
        self.transport_factory = Mock(return_value=self.transport)
        self.threads = NS(Thread=Mock(), Lock=threading.Lock, Event=threading.Event)
        owner = self

        class FakeNode:
            def __init__(self, name):
                self.get_logger = Mock()
                self.get_clock = lambda: NS(now=lambda: NS(to_msg=lambda: owner.stamp,
                    nanoseconds=owner.stamp.sec * 10**9 + owner.stamp.nanosec))
                self.create_publisher = Mock(side_effect=lambda *args: Mock())
                self.create_timer = Mock()
                self.get_parameters = Mock()
                self.list_parameters = lambda *args, **kwargs: NS(names=[])

            def declare_parameter(self, name, kind):
                return NS(value=owner.params[name])

            def destroy_node(self):
                pass

        path = PACKAGE / 'sensors/imu_sensor_node.py'
        cls = next(x for x in ast.parse(path.read_text()).body if isinstance(x, ast.ClassDef))
        scope = dict(Node=FakeNode, Parameter=NS(Type=NS(STRING=1, INTEGER=2, DOUBLE=3)),
                     Imu=Message, MagneticField=Message, ImuDriver=self.factory,
                     UartTransport=self.transport_factory, ORIENTATION_REPORTS={'rotation_vector': 5},
                     math=math, time=NS(monotonic=self.monotonic), threading=self.threads,
                     is_fresh=is_fresh,
                     Topics=NS(IMU_SENSOR_NODE=NS(PUB=NS(IMU_DATA='/imu/data', IMU_MAG='/imu/mag'))))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['ImuSensorNode']
        self.node = self.node_type()

    def test_reading_and_publication_are_separate(self):
        self.node.publish_imu()
        self.factory.assert_not_called()
        self.node.imu_pub.publish.assert_not_called()
        self.node.read_imu()
        self.driver.read.assert_called_once_with(wait_for_data=True)
        self.node.imu_pub.publish.assert_not_called()
        self.node.publish_imu()
        self.assertEqual(self.node.create_timer.call_args.args[0], 0.02)
        self.assertEqual(self.node.imu_pub.publish.call_args.args[0].orientation.w, 1.0)
        self.assertAlmostEqual(self.node.imu_pub.publish.call_args.args[0].orientation_covariance[8], 0.01)
        self.assertEqual(self.node.mag_pub.publish.call_args.args[0].magnetic_field.y, 2e-5)

    def test_polling_mode_does_not_wait_for_serial(self):
        self.node.read_rate_hz = 20.0
        self.node.read_imu()
        self.driver.read.assert_called_once_with(wait_for_data=False)

    def test_repetition_keeps_stamp_and_empty_reads_never_refresh_age(self):
        stamp = self.stamp
        self.node.read_imu()
        self.driver.read.return_value = None
        self.stamp = NS(sec=200, nanosec=100_000_000)
        self.node.read_imu()
        self.node.publish_imu()
        self.assertIs(self.node.imu_pub.publish.call_args.args[0].header.stamp, stamp)
        self.monotonic.return_value = 100.6
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_called_once()

    def test_ros_clock_forward_and_backward_jumps_reject_cached_data(self):
        self.node.read_imu()
        for seconds in (199, 201):
            self.stamp = NS(sec=seconds, nanosec=0)
            self.node.publish_imu()
        self.node.imu_pub.publish.assert_not_called()

    def test_magnetometer_expires_independently(self):
        self.node.read_imu()
        self.sample.magnetic_field = None
        self.sample.received_at = 100.6
        self.sample.oldest_received_at = 100.6
        self.monotonic.return_value = 100.6
        self.node.read_imu()
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_called_once()
        self.node.mag_pub.publish.assert_not_called()

    def test_latest_orientation_does_not_extend_old_component_lifetime(self):
        self.sample.received_at = 100.4
        self.sample.oldest_received_at = 100.0
        self.monotonic.return_value = 100.4
        self.node.read_imu()
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_called_once()
        self.monotonic.return_value = 100.6
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_called_once()

    def test_failure_clears_cache_closes_port_and_retries_with_ros_time_paused(self):
        self.node.read_imu()
        self.driver.read.side_effect = OSError('unplugged')
        self.node.read_imu()
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_not_called()
        self.transport.close.assert_called_once()
        self.node.read_imu()
        self.factory.assert_called_once()
        self.monotonic.return_value = 102.0
        self.sample.received_at = 102.0
        self.sample.oldest_received_at = 102.0
        self.driver.read.side_effect = None
        self.node.read_imu()
        self.node.publish_imu()
        self.assertEqual(self.factory.call_count, 2)
        self.node.imu_pub.publish.assert_called_once()

    def test_invalid_quaternion_clears_cached_data(self):
        self.node.read_imu()
        self.sample.orientation = (0, 0, 0, 0)
        self.node.read_imu()
        self.node.publish_imu()
        self.node.imu_pub.publish.assert_not_called()

    def test_shutdown_joins_reader_before_closing_uart(self):
        events = []
        self.node.read_imu()
        self.node._worker.join.side_effect = lambda: events.append('join')
        self.transport.close.side_effect = lambda: events.append('close')
        self.node.destroy_node()
        self.assertTrue(self.node._stop.is_set())
        self.assertEqual(events, ['join', 'close'])

    def test_invalid_timing_rejected_and_zero_read_rate_allowed(self):
        for name in ('read_rate_hz', 'publish_rate_hz', 'max_sample_age_s', 'timeout_s'):
            original = self.params[name]
            invalid = (-1.0, math.nan, math.inf) if name == 'read_rate_hz' else (0, -1, math.nan, math.inf)
            for value in invalid:
                with self.subTest(name=name, value=value):
                    self.params[name] = value
                    with self.assertRaisesRegex(ValueError, name):
                        self.node_type()
            self.params[name] = original
        self.transport_factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
