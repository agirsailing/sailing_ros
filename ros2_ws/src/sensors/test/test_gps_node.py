"""GPS acquisition, publication and serial cancellation without ROS/hardware."""

import ast
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(PACKAGE.parent / 'sail_common'))
from sail_common.freshness import is_fresh
from sensors.drivers.gps_driver import InterruptibleSerialStream, nav_pvt_values


def packet(**overrides):
    fields = dict(identity='NAV-PVT', lat=59.3, lon=18.1, hMSL=12000,
                  gSpeed=1500, headMot=123.4, pDOP=1.25, hAcc=500, vAcc=800,
                  numSV=12, fixType=3, gnssFixOk=1)
    fields.update(overrides)
    return NS(**fields)


class GpsMessage:
    COVARIANCE_TYPE_UNKNOWN = 0

    def __init__(self):
        self.header = NS(stamp=None, frame_id='')
        self.status = NS()


class GPSTests(unittest.TestCase):
    def setUp(self):
        self.params = dict(port='test', baudrate=230400, timeout_s=0.1,
                           read_rate_hz=0.0, publish_rate_hz=10.0,
                           max_sample_age_s=1.0, frame_id='gps', qos_depth=10)
        self.monotonic = Mock(return_value=100.0)
        self.stamp = NS(sec=200, nanosec=0)
        self.stream = Mock(in_waiting=0)
        self.serial = Mock(return_value=self.stream)
        self.reader = Mock()
        self.reader.read.return_value = (b'packet', packet())
        self.ubx = Mock(return_value=self.reader)
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

        path = PACKAGE / 'sensors/gps_node.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definition = next(item for item in tree.body if isinstance(item, ast.ClassDef))
        scope = dict(Node=FakeNode, Parameter=NS(Type=NS(STRING=1, INTEGER=2, DOUBLE=3)),
                     Serial=self.serial, UBXReader=self.ubx, GPSFix=GpsMessage,
                     GPSStatus=NS(STATUS_FIX=0, STATUS_NO_FIX=-1, SOURCE_GPS=1, SOURCE_NONE=0),
                     Topics=NS(GPS_NODE=NS(PUB=NS(GPS_DATA='/gps/data'))),
                     math=math, threading=self.threads, time=NS(monotonic=self.monotonic),
                     InterruptibleSerialStream=InterruptibleSerialStream,
                     nav_pvt_values=nav_pvt_values, is_fresh=is_fresh)
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), 'exec'), scope)
        self.node_type = scope['GPSNode']
        self.node = self.node_type()

    def test_publication_timer_does_not_read_and_waits_for_first_nav_pvt(self):
        self.node.create_timer.assert_called_once_with(0.1, self.node.publish_gps)
        self.node.publish_gps()
        self.reader.read.assert_not_called()
        self.node.gps_pub.publish.assert_not_called()

    def test_latest_packet_and_units_with_no_backlog_replay(self):
        for lat in (59.1, 59.2, 59.3):
            self.reader.read.return_value = (b'', packet(lat=lat))
            self.node._read_packet()
        self.node.publish_gps()
        self.node.gps_pub.publish.assert_called_once()
        msg = self.node.gps_pub.publish.call_args.args[0]
        self.assertEqual(msg.latitude, 59.3)
        self.assertEqual(msg.longitude, 18.1)
        self.assertEqual(msg.speed, 1.5)
        self.assertEqual(msg.track, 123.4)
        self.assertEqual(msg.altitude, 12.0)
        self.assertEqual(msg.pdop, 1.25)
        self.assertEqual(msg.status.satellites_used, 12)
        self.assertEqual(msg.header.frame_id, 'gps')
        self.assertEqual(msg.status.status, 0)
        self.assertEqual(msg.status.position_source, 1)
        self.assertEqual(msg.status.header, msg.header)

    def test_unknown_gpsfix_fields_are_not_fabricated(self):
        self.node._read_packet()
        self.node.publish_gps()
        msg = self.node.gps_pub.publish.call_args.args[0]
        for field in ('time', 'climb', 'pitch', 'roll', 'dip', 'err', 'err_horz',
                      'err_vert', 'err_track', 'err_speed', 'err_climb', 'err_time',
                      'err_pitch', 'err_roll', 'err_dip'):
            self.assertTrue(math.isnan(getattr(msg, field)), field)
        for field in ('gdop', 'hdop', 'vdop', 'tdop'):
            self.assertEqual(getattr(msg, field), -1.0)
        self.assertEqual(msg.position_covariance_type, 0)
        self.assertEqual(msg.status.motion_source, 0)
        self.assertEqual(msg.status.orientation_source, 0)

    def test_fix_type_is_mapped_to_status_not_copied_as_a_status_code(self):
        for fix_type in range(6):
            self.reader.read.return_value = (b'', packet(fixType=fix_type))
            self.node._read_packet()
            self.node.publish_gps()
            msg = self.node.gps_pub.publish.call_args.args[0]
            valid = fix_type in (2, 3, 4)
            self.assertEqual(msg.status.status, 0 if valid else -1)
            if fix_type in (3, 4):
                self.assertEqual(msg.altitude, 12.0)
            else:
                self.assertTrue(math.isnan(msg.altitude))
            if not valid:
                for field in ('latitude', 'longitude', 'speed', 'track'):
                    self.assertTrue(math.isnan(getattr(msg, field)))

    def test_no_fix_replaces_valid_fix_and_recovery_is_published(self):
        for flag in (1, 0, 1):
            self.reader.read.return_value = (b'', packet(gnssFixOk=flag))
            self.node._read_packet()
            self.node.publish_gps()
            msg = self.node.gps_pub.publish.call_args.args[0]
            self.assertEqual(msg.status.status, 0 if flag else -1)
            if not flag:
                self.assertTrue(math.isnan(msg.latitude))
        self.assertEqual(self.node.gps_pub.publish.call_count, 3)

    def test_repeated_publications_preserve_stamp_and_expire_without_packets(self):
        self.node._read_packet()
        original_stamp = self.stamp
        self.stamp = NS(sec=200, nanosec=500_000_000)
        self.monotonic.return_value = 100.5
        for _ in range(2):
            self.node.publish_gps()
            self.assertIs(self.node.gps_pub.publish.call_args.args[0].header.stamp, original_stamp)
        self.monotonic.return_value = 101.001
        self.node.publish_gps()
        self.assertEqual(self.node.gps_pub.publish.call_count, 2)

    def test_other_packets_and_idle_result_never_refresh_nav_pvt(self):
        self.node._read_packet()
        self.monotonic.return_value = 101.1
        for result in (None, NS(identity='NAV-STATUS'), NS(identity='GNGGA')):
            self.reader.read.return_value = (b'', result)
            self.node._read_packet()
            self.node.publish_gps()
        self.node.gps_pub.publish.assert_not_called()

    def test_source_clock_jump_rejects_cached_data(self):
        self.node._read_packet()
        for seconds in (199, 202):
            self.stamp = NS(sec=seconds, nanosec=0)
            self.node.publish_gps()
        self.node.gps_pub.publish.assert_not_called()

    def test_malformed_packet_clears_previous_value(self):
        self.node._read_packet()
        self.reader.read.return_value = (b'', NS(identity='NAV-PVT'))
        self.node._read_packet()
        self.node.publish_gps()
        self.node.gps_pub.publish.assert_not_called()

    def test_periodic_reads_drain_multiple_packets_before_waiting(self):
        self.node.read_rate_hz = 2.0
        self.stream.in_waiting = 300
        queue = [packet(lat=59.1), NS(identity='GNGGA'), packet(lat=59.5)]

        def read():
            result = queue.pop(0)
            if not queue:
                self.stream.in_waiting = 0
            return b'', result

        self.reader.read.side_effect = read
        self.node._stop = Mock()
        self.node._stop.is_set.return_value = False
        self.node._stop.wait.side_effect = lambda delay: setattr(
            self.node._stop.is_set, 'return_value', True)
        self.node._read_loop()
        self.node._stop.wait.assert_called_once_with(0.5)
        self.assertEqual(self.reader.read.call_count, 3)
        self.node.publish_gps()
        self.assertEqual(self.node.gps_pub.publish.call_args.args[0].latitude, 59.5)

    def test_serial_failure_clears_cache_and_backs_off(self):
        self.node._read_packet()
        self.reader.read.side_effect = OSError('disconnected')
        self.node._stop = Mock()
        self.node._stop.is_set.return_value = False
        self.node._stop.wait.side_effect = lambda delay: setattr(
            self.node._stop.is_set, 'return_value', True)
        self.node._read_loop()
        self.node._stop.wait.assert_any_call(0.1)
        self.node.publish_gps()
        self.node.gps_pub.publish.assert_not_called()

    def test_failed_parser_setup_closes_port(self):
        self.ubx.side_effect = ValueError('parser failed')
        with self.assertRaisesRegex(ValueError, 'parser failed'):
            self.node_type()
        self.stream.close.assert_called_once()

    def test_shutdown_interrupts_idle_reader_and_joins_before_close(self):
        entered = threading.Event()

        def read_serial(size):
            entered.set()
            threading.Event().wait(0.01)
            return b''

        self.stream.read.side_effect = read_serial
        self.ubx.side_effect = lambda stream: NS(read=lambda: (stream.read(4), None))
        self.threads.Thread = threading.Thread
        node = self.node_type()
        self.stream.close.side_effect = lambda: self.assertFalse(node._reader_thread.is_alive())
        try:
            self.assertTrue(entered.wait(1.0))
        finally:
            node.destroy_node()
        self.stream.close.assert_called_once()
        self.assertTrue(node.destroyed)

    def test_invalid_rates_and_timeouts_are_rejected_before_opening(self):
        for key, value in (('read_rate_hz', -1.0), ('read_rate_hz', math.nan),
                           ('publish_rate_hz', 0.0), ('publish_rate_hz', math.inf),
                           ('timeout_s', 0.0), ('max_sample_age_s', -1.0)):
            old = self.params[key]
            self.params[key] = value
            self.serial.reset_mock()
            with self.assertRaisesRegex(ValueError, key):
                self.node_type()
            self.serial.assert_not_called()
            self.params[key] = old


class SerialAdapterTests(unittest.TestCase):
    def test_partial_packet_survives_timeouts(self):
        stream = Mock()
        stream.read.side_effect = [b'\xb5', b'', b'\x62', b'', b'\x01\x07']
        adapter = InterruptibleSerialStream(stream, threading.Event())
        self.assertEqual(adapter.read(4), b'\xb5\x62\x01\x07')
        self.assertEqual([call.args[0] for call in stream.read.call_args_list], [4, 3, 3, 2, 2])

    def test_mixed_nmea_line_survives_timeout_and_stops_at_newline(self):
        stream = Mock()
        stream.read.side_effect = [b'G', b'', b'P', b'\r', b'\n']
        adapter = InterruptibleSerialStream(stream, threading.Event())
        self.assertEqual(adapter.readline(), b'GP\r\n')

    def test_stop_releases_partial_read(self):
        stop = threading.Event()
        stream = Mock()

        def read(size):
            stop.set()
            return b'\xb5'

        stream.read.side_effect = read
        self.assertEqual(InterruptibleSerialStream(stream, stop).read(4), b'\xb5')
        stream.read.assert_called_once()


if __name__ == '__main__':
    unittest.main()
