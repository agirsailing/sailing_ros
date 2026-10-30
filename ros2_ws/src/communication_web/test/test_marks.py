"""Course mark capture, MQTT duplicate handling, and failure semantics."""

from concurrent.futures import Future
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'test'))
from communication_web.gateway.mark_rpc import MarkRpc
from communication_web.generated.ros_endpoints import Services, Topics
import test_wiring as wiring


class CaptureTests(unittest.TestCase):
    def setUp(self):
        factory = wiring.WiringTests()
        factory.setUp()
        self.node = factory.telemetry_node()

    def gps(self, stamp=100, status=0, lat=59.123456789, lon=18.987654321):
        msg = NS(header=NS(stamp=NS(sec=stamp, nanosec=0), frame_id='gps'),
                 status=NS(status=status), latitude=lat, longitude=lon, speed=float('nan'))
        self.node._receive('gps', msg)
        return msg

    def ping(self, kind):
        return self.node._ping_mark(NS(type=kind), NS(success=False, error_message='', mark=None))

    def test_capture_preserves_source_precision_and_replaces_only_selected_type(self):
        gps = self.gps()
        for kind in (0, 1, 2):
            reply = self.ping(kind)
            self.assertTrue(reply.success)
            self.assertEqual(reply.mark.lat, gps.latitude)
            self.assertEqual(reply.mark.header, gps.header)
        self.gps(lat=60.123456789)
        self.assertTrue(self.ping(1).success)
        self.node.publish_map()
        state = self.node.position_pub.publish.call_args.args[0]
        self.assertEqual([mark.type for mark in state.marks], [0, 1, 2])
        self.assertEqual(state.marks[0].lat, gps.latitude)
        self.assertEqual(state.marks[1].lat, 60.123456789)
        # Captured course state is independent of live GPS freshness/validity.
        self.gps(status=-1)
        self.node.publish_map()
        state = self.node.position_pub.publish.call_args.args[0]
        self.assertFalse(state.fix_valid)
        self.assertEqual(len(state.marks), 3)

    def test_bad_missing_old_future_gps_and_unknown_type_never_change_saved_marks(self):
        self.assertFalse(self.ping(0).success)
        self.gps()
        self.assertTrue(self.ping(0).success)
        original = self.node.marks[0]
        for kwargs in ({'stamp': 97}, {'stamp': 101}, {'status': -1},
                       {'lat': float('nan')}, {'lat': 91}, {'lon': 181}):
            self.gps(**kwargs)
            self.assertFalse(self.ping(0).success)
            self.assertIs(self.node.marks[0], original)
        self.gps()
        self.assertFalse(self.ping(99).success)
        self.assertEqual(len(self.node.marks), 1)

    def test_ping_queue_is_processed_on_timer_and_ignores_retained_messages(self):
        factory = wiring.WiringTests()
        factory.setUp()
        node = factory.command_node()
        self.assertEqual(Services.COMMAND_GATEWAY_NODE.SRV.PING_MARK,
                         Services.TELEMETRY_GATEWAY_NODE.SRV.PING_MARK)
        topic = Topics.COMMAND_GATEWAY_NODE.MQTT.SUB.PING_MARK
        node.ping_client.service_is_ready.return_value = True
        node.ping_client.call_async.return_value = Future()
        node._enqueue_command(topic, b'{"requestId":"ping-1","type":2}', True)
        node._process_commands()
        node.ping_client.call_async.assert_not_called()
        node._enqueue_command(topic, b'{"requestId":"ping-1","type":2}', False)
        node.ping_client.call_async.assert_not_called()
        node._process_commands()
        self.assertEqual(node.ping_client.call_async.call_args.args[0].type, 2)
        node.start_client.call_async.assert_not_called()


class RpcTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.service_is_ready.return_value = True
        self.future = Future()
        self.client.call_async.return_value = self.future
        self.publish = Mock()
        self.rpc = MarkRpc(self.client, NS, self.publish, 'response', 5.0, 2)

    def send(self, kind=0, request_id='one'):
        self.rpc.handle(json.dumps(dict(requestId=request_id, type=kind)))

    def reply(self):
        return self.publish.call_args.args[1]

    def test_duplicate_qos_delivery_does_not_recapture_and_reused_id_cannot_change_type(self):
        self.send()
        self.send()
        self.client.call_async.assert_called_once()
        mark = NS(type=0, lat=59.1, lon=18.1,
                  header=NS(frame_id='gps', stamp=NS(sec=99, nanosec=2)))
        self.future.set_result(NS(success=True, error_message='', mark=mark))
        self.rpc.poll()
        response = self.reply()
        self.assertEqual(response['mark']['header']['stamp'], {'sec': 99, 'nanosec': 2})
        self.send()
        self.assertEqual(self.reply(), response)
        self.client.call_async.assert_called_once()
        self.send(kind=1)
        self.assertFalse(self.reply()['success'])
        self.client.call_async.assert_called_once()

    def test_invalid_payloads_and_retained_commands_do_not_call_ros(self):
        self.rpc.handle(b'{"requestId":"old","type":0}', retained=True)
        self.publish.assert_not_called()
        for payload in ('{', '[]', '{}', '{"requestId":"a","type":true}',
                        '{"requestId":"a","type":3}', '{"requestId":"a","type":"1"}',
                        '{"requestId":"a","type":0,"lat":59,"lon":18}'):
            self.rpc.handle(payload)
            self.assertFalse(self.reply()['success'])
        self.client.call_async.assert_not_called()

    def test_unavailable_busy_service_errors_and_timeout_are_reported_without_retry(self):
        self.client.service_is_ready.return_value = False
        self.send(request_id='unavailable')
        self.assertIn('unavailable', self.reply()['error_message'])
        self.client.service_is_ready.return_value = True
        with patch('communication_web.gateway.mark_rpc.time.monotonic', return_value=10):
            self.send()
        self.send(request_id='busy')
        self.assertIn('pending', self.reply()['error_message'])
        with patch('communication_web.gateway.mark_rpc.time.monotonic', return_value=16):
            self.rpc.poll()
        self.assertIn('outcome unknown', self.reply()['error_message'])
        self.assertTrue(self.future.cancelled())
        self.send(request_id='busy')
        self.assertIn('pending', self.reply()['error_message'])
        self.client.call_async.assert_called_once()
        self.send()
        self.client.call_async.assert_called_once()
        self.future = Future()
        self.client.call_async.return_value = self.future
        self.send(request_id='error')
        self.future.set_exception(RuntimeError('test failure'))
        self.rpc.poll()
        self.assertFalse(self.reply()['success'])
        self.assertEqual(len(self.rpc.completed), 2)


if __name__ == '__main__':
    unittest.main()
