"""Offline behavior tests: no ROS, MQTT client, subprocesses or hardware."""

import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from communication_web.gateway.recording_rpc import RecordingRpc
from communication_web.gateway.telemetry import TelemetrySnapshot, json_safe


def stamp(value=100):
    return NS(sec=int(value), nanosec=round((value - int(value)) * 1e9))


def sample(**fields):
    return NS(header=NS(stamp=stamp()), **fields)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.state = TelemetrySnapshot(0.5, 0.5, 3.0, 2.0)

    def populate(self):
        self.state.update('attitude', sample(roll_deg=12.0, pitch_deg=-3.0, yaw_deg=375.0), 100)
        self.state.update('height', sample(height_m=-0.05), 100)
        self.state.update('battery', NS(data=False), 100)
        self.state.update('gps', sample(gps_stamp=stamp(), fix_valid=True,
                                       latitude_deg=59.3, longitude_deg=18.0, sog_mps=6.2), 100)

    def test_missing_inputs_are_unknown_and_valid_json(self):
        telemetry, position, gps_stamp = self.state.build(100)
        self.assertFalse(telemetry['battery_valid'])
        self.assertFalse(telemetry['attitude_valid'])
        self.assertFalse(position['fix_valid'])
        self.assertIsNone(gps_stamp)
        result = json.loads(json.dumps(json_safe(telemetry), allow_nan=False))
        self.assertIsNone(result['height_m'])
        self.assertIsNone(result['roll_deg'])

    def test_degrees_signed_height_and_mps_are_preserved(self):
        self.populate()
        data, position, source_stamp = self.state.build(100.1)
        self.assertEqual((data['roll_deg'], data['pitch_deg'], data['yaw_deg']), (12, -3, 375))
        self.assertEqual(data['height_m'], -0.05)
        self.assertTrue(data['battery_valid'])
        self.assertFalse(data['battery_low'])
        self.assertEqual(data['sog_mps'], 6.2)
        self.assertEqual(position['sog_mps'], 6.2)
        self.assertEqual(source_stamp.sec, 100)

    def test_inputs_expire_independently(self):
        self.populate()
        data, position, _ = self.state.build(101)
        self.assertFalse(data['attitude_valid'])
        self.assertFalse(data['height_valid'])
        self.assertTrue(position['fix_valid'])
        self.assertTrue(data['battery_valid'])
        data, position, _ = self.state.build(104)
        self.assertFalse(position['fix_valid'])
        self.assertFalse(data['battery_valid'])

    def test_fresh_summary_cannot_refresh_stale_gps(self):
        self.state.update('gps', sample(gps_stamp=stamp(90), fix_valid=True,
                                       latitude_deg=59.3, longitude_deg=18.0, sog_mps=6.2), 100)
        data, position, source_stamp = self.state.build(100)
        self.assertFalse(position['fix_valid'])
        self.assertFalse(data['sog_valid'])
        self.assertEqual(source_stamp.sec, 90)

    def test_invalid_coordinates_fix_speed_and_nonfinite_values(self):
        for fields in (dict(latitude_deg=91), dict(longitude_deg=181),
                       dict(fix_valid=False), dict(sog_mps=-1), dict(sog_mps=float('inf'))):
            with self.subTest(fields=fields):
                self.populate()
                msg, received = self.state.samples['gps']
                for key, value in fields.items():
                    setattr(msg, key, value)
                data, position, _ = self.state.build(100)
                self.assertFalse(position['fix_valid'])
                self.assertFalse(data['sog_valid'])

    def test_nonfinite_attitude_does_not_invalidate_height(self):
        self.populate()
        self.state.samples['attitude'][0].roll_deg = float('nan')
        data, _, _ = self.state.build(100)
        self.assertFalse(data['attitude_valid'])
        self.assertTrue(data['height_valid'])

    def test_future_source_stamp_rejected(self):
        self.populate()
        self.state.samples['attitude'][0].header.stamp = stamp(102)
        self.assertFalse(self.state.build(100)[0]['attitude_valid'])

    def test_clock_rewind_clears_old_samples(self):
        self.populate()
        self.state.build(100.1)
        data, position, gps_stamp = self.state.build(99)
        self.assertFalse(data['battery_valid'])
        self.assertFalse(position['fix_valid'])
        self.assertIsNone(gps_stamp)
        self.assertFalse(self.state.build(100)[0]['attitude_valid'])

    def test_nested_json_is_standard(self):
        cleaned = json_safe({'array': [float('inf'), float('-inf'), float('nan'), 4.0]})
        self.assertEqual(cleaned, {'array': [None, None, None, 4.0]})
        json.dumps(cleaned, allow_nan=False)


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.future = Mock()
        self.future.done.return_value = False
        self.start = Mock()
        self.stop = Mock()
        for client in (self.start, self.stop):
            client.service_is_ready.return_value = True
            client.call_async.return_value = self.future
        self.publish = Mock()
        self.rpc = RecordingRpc({
            'start': (self.start, object, 'start_response', 'effective_bag_name'),
            'stop': (self.stop, object, 'stop_response', 'last_bag_name'),
        }, self.publish, 15.0, 2)

    def command(self, topic='start', request_id='request-1', retained=False):
        self.rpc.handle(topic, json.dumps({'requestId': request_id}).encode(), retained)

    def test_start_and_stop_report_actual_service_bag_fields(self):
        for command, field in (('start', 'effective_bag_name'), ('stop', 'last_bag_name')):
            with self.subTest(command=command):
                self.command(command, command)
                self.future.done.return_value = True
                self.future.result.return_value = NS(success=True, error_message='', **{field: 'bag-1'})
                self.rpc.poll()
                self.assertEqual(self.publish.call_args.args,
                                 (command + '_response', dict(requestId=command, success=True,
                                  error_message='', bag_name='bag-1')))

    def test_only_two_allowed_commands(self):
        self.command('shutdown')
        self.start.call_async.assert_not_called()
        self.stop.call_async.assert_not_called()
        self.publish.assert_not_called()

    def test_retained_command_is_never_executed(self):
        self.command(retained=True)
        self.start.call_async.assert_not_called()

    def test_malformed_missing_or_nonstring_request_id(self):
        for payload in (b'{', b'[]', b'{}', b'{"requestId":1}', b'{"requestId":" "}', b'\xff'):
            with self.subTest(payload=payload):
                self.rpc.handle('start', payload, False)
                self.assertFalse(self.publish.call_args.args[1]['success'])
        self.start.call_async.assert_not_called()

    def test_unavailable_service(self):
        self.start.service_is_ready.return_value = False
        self.command()
        self.start.call_async.assert_not_called()
        self.assertIn('unavailable', self.publish.call_args.args[1]['error_message'])

    def test_pending_duplicate_does_not_repeat_service(self):
        self.command()
        self.command()
        self.start.call_async.assert_called_once()
        self.publish.assert_not_called()

    def test_completed_duplicate_replays_response(self):
        self.command()
        self.future.done.return_value = True
        self.future.result.return_value = NS(success=True, error_message='', effective_bag_name='bag-1')
        self.rpc.poll()
        first = self.publish.call_args
        self.command()
        self.start.call_async.assert_called_once()
        self.assertEqual(self.publish.call_args, first)

    def test_pending_request_serializes_commands(self):
        self.command()
        self.command('stop', 'request-2')
        self.stop.call_async.assert_not_called()
        self.assertIn('pending', self.publish.call_args.args[1]['error_message'])

    def test_reusing_id_for_different_command_is_rejected(self):
        self.start.service_is_ready.return_value = False
        self.command()
        self.command('stop')
        self.stop.call_async.assert_not_called()
        self.assertIn('another command', self.publish.call_args.args[1]['error_message'])

    def test_timeout_removes_future_and_reports_unknown_outcome(self):
        with patch('communication_web.gateway.recording_rpc.time.monotonic', return_value=10):
            self.command()
        with patch('communication_web.gateway.recording_rpc.time.monotonic', return_value=26):
            self.rpc.poll()
        self.start.remove_pending_request.assert_called_once_with(self.future)
        self.future.cancel.assert_called_once()
        self.assertIsNone(self.rpc.pending)
        self.assertIn('unknown', self.publish.call_args.args[1]['error_message'])

    def test_service_exception_is_a_failed_reply(self):
        self.command()
        self.future.done.return_value = True
        self.future.result.side_effect = RuntimeError('failed')
        self.rpc.poll()
        self.assertFalse(self.publish.call_args.args[1]['success'])

    def test_response_cache_is_bounded(self):
        self.start.service_is_ready.return_value = False
        for index in range(3):
            self.command(request_id=str(index))
        self.assertEqual(list(self.rpc.completed), ['1', '2'])


if __name__ == '__main__':
    unittest.main()
