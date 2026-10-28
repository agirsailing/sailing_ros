"""UART framing, SH-2 decoding and per-stream freshness without hardware."""

from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock, patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PACKAGE), str(PACKAGE.parent / 'sail_common')]
from sensors.drivers import imu_driver as driver


def packet(channel, payload):
    return struct.pack('<HBB', len(payload) + 4, channel, 0) + payload


def report(report_id, values):
    return bytes([report_id, 0, 3, 0]) + struct.pack('<' + 'h' * len(values), *values)


class BnoDriverTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(driver.time, 'monotonic', return_value=100.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.sleep = patch.object(driver.time, 'sleep').start()
        self.addCleanup(patch.stopall)
        self.transport = Mock()
        self.transport.receive.side_effect = [[], [packet(driver.CHANNEL_CONTROL, b'\xf8')]]
        self.sensor = driver.ImuDriver(self.transport, 0.01, 0.02)
        self.transport.receive.side_effect = None
        self.transport.receive.return_value = []

    def feed(self, payload):
        self.transport.receive.return_value = [packet(driver.CHANNEL_REPORTS, payload)]
        value = self.sensor.read(wait_for_data=True)
        self.transport.receive.return_value = []
        return value

    def all_reports(self):
        return (report(driver.REPORT_ACCELEROMETER, [256, -512, 2510])
                + report(driver.REPORT_GYROSCOPE, [512, -1024, 0])
                + report(driver.REPORT_MAGNETOMETER, [160, -320, 480])
                + report(driver.REPORT_ROTATION_VECTOR, [0, 0, 0, 16384, 4096]))

    def test_feature_commands_request_fusion_and_independent_rates(self):
        sent = [call.args[0][4:] for call in self.transport.send.call_args_list]
        features = [struct.unpack('<BBBHIII', p) for p in sent if p[0] == 0xFD]
        self.assertEqual([(f[1], f[4]) for f in features], [(5, 10000), (1, 10000),
                                                                     (2, 10000), (3, 20000)])

    def test_decode_units_quaternion_accuracy_and_no_repeat_without_new_orientation(self):
        sample = self.feed(self.all_reports())
        self.assertEqual(sample.orientation, (0, 0, 0, 1))
        self.assertEqual(sample.acceleration[:2], (1, -2))
        self.assertEqual(sample.angular_velocity, (1, -2, 0))
        self.assertAlmostEqual(sample.magnetic_field[1], -20e-6)
        self.assertEqual(sample.heading_accuracy_rad, 1.0)
        self.assertEqual(sample.orientation_accuracy, 3)
        self.assertEqual(sample.received_at, 100.0)
        self.assertIsNone(self.sensor.read())
        self.assertIsNone(self.feed(report(driver.REPORT_GYROSCOPE, [0, 0, 0])))

    def test_new_orientation_cannot_refresh_stopped_acceleration_or_gyro(self):
        self.feed(self.all_reports())
        self.now.return_value = 100.6
        orientation = report(driver.REPORT_ROTATION_VECTOR, [0, 0, 0, 16384, 4096])
        self.assertIsNone(self.feed(orientation))
        self.assertIsNotNone(self.feed(self.all_reports()))

    def test_magnetic_timestamp_is_not_renewed_by_orientation(self):
        self.feed(self.all_reports())
        self.now.return_value = 100.1
        sample = self.feed(report(driver.REPORT_ROTATION_VECTOR, [0, 0, 0, 16384, 0]))
        self.assertIsNone(sample.magnetic_field)
        self.assertEqual(sample.received_at, 100.1)
        self.assertEqual(sample.oldest_received_at, 100.0)
        self.assertEqual(sample.magnetic_received_at, 100.0)

    def test_reset_and_silence_trigger_reconnection(self):
        with self.assertRaisesRegex(OSError, 'reset unexpectedly'):
            self.sensor._handle(driver.CHANNEL_EXECUTABLE, b'\x01')
        self.now.return_value = 101.1
        with self.assertRaisesRegex(OSError, 'stopped reporting'):
            self.sensor.read()

    def test_partial_escaped_frames_recover_after_garbage_and_invalid_length(self):
        decoder = driver.UartFrameDecoder()
        valid = packet(3, b'\x7e\x7d\x01')
        encoded = driver.uart_frame(valid)
        self.assertEqual(decoder.feed(b'garbage' + encoded[:4]), [])
        self.assertEqual(decoder.feed(encoded[4:]), [valid])
        corrupt = driver.uart_frame(b'\x20\x00\x03\x00\x01')
        self.assertEqual(decoder.feed(corrupt + encoded), [valid])
        self.assertEqual(decoder.feed(b'\x7e\x01\x7d\x7e' + encoded), [valid])

    def test_oversized_and_fragmented_packets_are_not_decoded(self):
        decoder = driver.UartFrameDecoder()
        data = b'\x7e\x01' + b'\x7d\x20' * (driver.MAX_PACKET_BYTES + 5)
        self.assertEqual(decoder.feed(data + b'\x7e'), [])
        self.assertGreater(decoder.dropped_frames, 0)
        self.assertEqual(decoder.feed(driver.uart_frame(b'\x04\x80\x03\x00')), [])

    def test_uart_arrival_mode_blocks_for_one_byte_then_drains_buffer(self):
        stream = Mock()
        factory = Mock(return_value=stream)
        transport = driver.UartTransport('/dev/test', serial_factory=factory, timeout_s=0.1)
        factory.assert_called_once_with('/dev/test', 3000000, timeout=0.1, write_timeout=1.0)
        stream.in_waiting = 0
        self.assertEqual(transport.receive(), [])
        stream.read.assert_not_called()
        encoded = driver.uart_frame(packet(3, b'abc'))
        type(stream).in_waiting = property(lambda _: next(waiting))
        waiting = iter([0, len(encoded)-1])
        stream.read.side_effect = [encoded[:1], encoded[1:]]
        self.assertEqual(transport.receive(wait_for_data=True), [packet(3, b'abc')])
        self.assertEqual([c.args[0] for c in stream.read.call_args_list], [1, len(encoded)-1])
        transport.close()
        stream.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
