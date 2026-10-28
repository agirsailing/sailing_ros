"""BNO085 acquisition (SH-2 over SHTP): fused orientation plus 9-DOF data.

The sensor runs CEVA (Hillcrest) SH-2 firmware. The host enables reports at a
chosen interval and the sensor streams them; this driver frames SHTP packets
and decodes the reports it enabled. No filtering or frame conversion here.

Transport: full SHTP UART mode (PS1/P1 high, PS0/P0 low), fixed 3 Mbaud,
on the Raspberry Pi GPIO UART. This is NOT UART-RVC mode (P0 high), which has
no gyroscope output. The transport only moves complete SHTP packets, so
another one (I2C, SPI) can be added without touching the SH-2 layer.

Axes are the breakout's printed X/Y/Z. The rotation vector is the body
orientation relative to an East-North-Up world referenced to MAGNETIC north
and gravity. The game rotation vector has no heading reference.
"""

from dataclasses import dataclass
import math
import struct
import time
from sail_common.freshness import is_fresh

# SHTP channels.
CHANNEL_COMMAND = 0
CHANNEL_EXECUTABLE = 1
CHANNEL_CONTROL = 2
CHANNEL_REPORTS = 3
CHANNEL_COUNT = 6

# SH-2 identifiers.
EXECUTABLE_RESET = 0x01         # host->sensor: reset; sensor->host: reset complete
PRODUCT_ID_REQUEST = 0xF9
PRODUCT_ID_RESPONSE = 0xF8
SET_FEATURE_COMMAND = 0xFD
TIMESTAMP_REBASE = 0xFA
BASE_TIMESTAMP = 0xFB

REPORT_ACCELEROMETER = 0x01
REPORT_GYROSCOPE = 0x02
REPORT_MAGNETOMETER = 0x03
REPORT_ROTATION_VECTOR = 0x05
REPORT_GAME_ROTATION_VECTOR = 0x08

# Report ID -> (length including the 4-byte report header, Q point).
SENSOR_REPORTS = {
    REPORT_ACCELEROMETER: (10, 8),          # m/s^2, gravity included
    REPORT_GYROSCOPE: (10, 9),              # rad/s, calibrated
    REPORT_MAGNETOMETER: (10, 4),           # uT, calibrated
    REPORT_ROTATION_VECTOR: (14, 14),       # i, j, k, real + heading accuracy
    REPORT_GAME_ROTATION_VECTOR: (12, 14),  # i, j, k, real
}
ORIENTATION_REPORTS = {
    'rotation_vector': REPORT_ROTATION_VECTOR,
    'game_rotation_vector': REPORT_GAME_ROTATION_VECTOR,
}
HEADING_ACCURACY_Q = 12
MAX_PACKET_BYTES = 1024
SHTP_HEADER_BYTES = 4

# SHTP-over-UART framing (HDLC-like).
UART_FLAG = 0x7E
UART_ESCAPE = 0x7D
UART_PROTOCOL_SHTP = 0x01
UART_BAUDRATE = 3_000_000


def shtp_length(packet):
    return (packet[0] | packet[1] << 8) & 0x7FFF


# -----------------------
#   UART transport: send/receive complete SHTP packets (header included)
# -----------------------
class UartFrameDecoder:
    """Turn the 0x7E-delimited, byte-stuffed UART stream into SHTP packets."""

    def __init__(self):
        self.in_frame = False
        self.escape = False
        self.buffer = bytearray()
        self.dropped_frames = 0

    def feed(self, data):
        packets = []
        for byte in data:
            if byte == UART_FLAG:
                # A flag ends the current frame and may start the next one.
                if self.in_frame and self.buffer:
                    packet = None if self.escape else self._finish(bytes(self.buffer))
                    if packet is not None:
                        packets.append(packet)
                self.in_frame, self.escape = True, False
                self.buffer.clear()
            elif not self.in_frame:
                continue                      # Discard bytes before the first flag.
            elif self.escape:
                self.buffer.append(byte ^ 0x20)
                self.escape = False
            elif byte == UART_ESCAPE:
                self.escape = True
            else:
                self.buffer.append(byte)
            if len(self.buffer) > MAX_PACKET_BYTES + 1:
                self.dropped_frames += 1  # Lost flag: resynchronize.
                self.in_frame = False
                self.buffer.clear()
        return packets

    def _finish(self, frame):
        # Frame: protocol ID, then an SHTP packet. Other protocols are ignored.
        if frame[0] != UART_PROTOCOL_SHTP or len(frame) < 1 + SHTP_HEADER_BYTES:
            self.dropped_frames += 1
            return None
        packet = frame[1:]
        length = shtp_length(packet)
        # Fragmented packets are not assembled by this driver. Reject them
        # rather than parsing an incomplete report as a fresh measurement.
        if packet[1] & 0x80 or length != len(packet) or length < SHTP_HEADER_BYTES:
            self.dropped_frames += 1
            return None
        return packet[:length]


def uart_frame(packet):
    stuffed = bytearray([UART_FLAG, UART_PROTOCOL_SHTP])
    for byte in packet:
        if byte in (UART_FLAG, UART_ESCAPE):
            stuffed += bytes([UART_ESCAPE, byte ^ 0x20])
        else:
            stuffed.append(byte)
    stuffed.append(UART_FLAG)
    return bytes(stuffed)


class UartTransport:
    def __init__(self, port, baudrate=UART_BAUDRATE, inter_byte_delay_s=0.001,
                 serial_factory=None, timeout_s=0.1):
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self.inter_byte_delay_s = inter_byte_delay_s
        self.decoder = UartFrameDecoder()
        self.serial = serial_factory(port, baudrate, timeout=timeout_s, write_timeout=1.0)
        try:
            # Reduce USB-serial buffering latency where the driver supports it.
            self.serial.set_low_latency_mode(True)
        except (AttributeError, OSError, ValueError):
            pass
        self.serial.reset_input_buffer()

    def send(self, packet):
        # The sensor's UART receiver needs a gap between host bytes. Writes only
        # happen during initialization, so a slow byte-by-byte write is fine.
        for byte in uart_frame(packet):
            self.serial.write(bytes([byte]))
            self.serial.flush()
            time.sleep(self.inter_byte_delay_s)

    def receive(self, wait_for_data=False):
        waiting = self.serial.in_waiting
        if not waiting and not wait_for_data:
            return []
        # In arrival mode, block for one byte then drain everything already
        # buffered. Partial UART frames survive idle read timeouts.
        data = self.serial.read(waiting or 1)
        waiting = self.serial.in_waiting
        if waiting:
            data += self.serial.read(waiting)
        return self.decoder.feed(data)

    def close(self):
        self.serial.close()


# -----------------------
#   SH-2 protocol
# -----------------------
@dataclass(frozen=True)
class ImuSample:
    orientation: tuple            # (x, y, z, w): body -> world quaternion
    orientation_accuracy: int     # SH-2 status: 0 unreliable .. 3 high
    heading_accuracy_rad: float   # NaN for the game rotation vector
    acceleration: tuple           # m/s^2, gravity included
    angular_velocity: tuple       # rad/s
    magnetic_field: tuple         # tesla; None unless a new report arrived
    magnetic_accuracy: int        # SH-2 status; -1 before the first report
    received_at: float            # host monotonic time of orientation decoding
    magnetic_received_at: float   # independent magnetic-report decoding time


class ImuDriver:
    def __init__(self, transport, report_interval_s, magnetometer_interval_s,
                 orientation_report='rotation_vector', reset_delay_s=0.5,
                 response_timeout_s=1.0, stale_timeout_s=1.0, max_sample_age_s=0.5):
        if orientation_report not in ORIENTATION_REPORTS:
            raise ValueError(f'Unknown orientation report: {orientation_report}')
        if not report_interval_s > 0 or not magnetometer_interval_s > 0:
            raise ValueError('Report intervals must be positive')
        self.transport = transport
        self.orientation_id = ORIENTATION_REPORTS[orientation_report]
        self.stale_timeout_s = stale_timeout_s
        self.max_sample_age_s = max_sample_age_s
        self._sequence = [0] * CHANNEL_COUNT
        self._latest = {}            # report ID -> (values, accuracy)
        self._received_at = {}       # report ID -> host monotonic decoding time
        self._fresh_orientation = False
        self._fresh_magnetometer = False
        self._product_seen = False
        self._ready = False

        # Soft reset, then drain the advertisement and reset-complete packets.
        self._send(CHANNEL_EXECUTABLE, [EXECUTABLE_RESET])
        time.sleep(reset_delay_s)
        deadline = time.monotonic() + response_timeout_s
        while self._poll():
            if time.monotonic() >= deadline:
                raise OSError('BNO085 did not settle after reset')

        # Confirm an SH-2 device answers before enabling reports. Packets queued
        # before its reply (e.g. a late reset-complete) are consumed here.
        self._send(CHANNEL_CONTROL, [PRODUCT_ID_REQUEST, 0])
        deadline = time.monotonic() + response_timeout_s
        while not self._product_seen:
            if time.monotonic() > deadline:
                raise OSError('No SH-2 product ID response; check wiring, the '
                              'PS0/PS1 mode pins and the converter baud rate')
            time.sleep(0.01)
            self._poll()

        for report_id, interval in (
                (self.orientation_id, report_interval_s),
                (REPORT_ACCELEROMETER, report_interval_s),
                (REPORT_GYROSCOPE, report_interval_s),
                (REPORT_MAGNETOMETER, magnetometer_interval_s)):
            self._send(CHANNEL_CONTROL, struct.pack(
                '<BBBHIII', SET_FEATURE_COMMAND, report_id, 0, 0,
                int(round(interval * 1e6)), 0, 0))
        self._ready = True
        self._last_packet_s = time.monotonic()

    # -----------------------
    #   Public API
    # -----------------------
    def read(self, wait_for_data=False):
        """Process received packets; return a sample when a new orientation arrived."""
        packets = self._poll(wait_for_data)
        now = time.monotonic()
        if packets:
            self._last_packet_s = now
        elif now - self._last_packet_s > self.stale_timeout_s:
            raise OSError('BNO085 stopped reporting')
        required = (self.orientation_id, REPORT_ACCELEROMETER, REPORT_GYROSCOPE)
        if not self._fresh_orientation or any(r not in self._latest for r in required):
            return None
        self._fresh_orientation = False
        # A live orientation stream must not indefinitely reuse stopped gyro or
        # accelerometer reports. Each stream has its own decoding timestamp.
        if any(not is_fresh(self._received_at[r], now, self.max_sample_age_s)
               for r in required):
            return None
        (quaternion, heading_accuracy), orientation_accuracy = self._latest[self.orientation_id]
        magnetic_field, magnetic_accuracy = None, -1
        if REPORT_MAGNETOMETER in self._latest:
            values, magnetic_accuracy = self._latest[REPORT_MAGNETOMETER]
            if (self._fresh_magnetometer and is_fresh(
                    self._received_at[REPORT_MAGNETOMETER], now, self.max_sample_age_s)):
                magnetic_field = values
                self._fresh_magnetometer = False
        return ImuSample(
            orientation=quaternion,
            orientation_accuracy=orientation_accuracy,
            heading_accuracy_rad=heading_accuracy,
            acceleration=self._latest[REPORT_ACCELEROMETER][0],
            angular_velocity=self._latest[REPORT_GYROSCOPE][0],
            magnetic_field=magnetic_field,
            magnetic_accuracy=magnetic_accuracy,
            received_at=self._received_at[self.orientation_id],
            magnetic_received_at=self._received_at.get(REPORT_MAGNETOMETER))

    def close(self):
        self.transport.close()

    # -----------------------
    #   SHTP packets
    # -----------------------
    def _send(self, channel, payload):
        payload = bytes(payload)
        length = len(payload) + SHTP_HEADER_BYTES
        sequence = self._sequence[channel]
        self._sequence[channel] = (sequence + 1) & 0xFF
        self.transport.send(bytes([length & 0xFF, length >> 8, channel, sequence]) + payload)

    def _poll(self, wait_for_data=False):
        packets = self.transport.receive(wait_for_data=wait_for_data)
        for packet in packets:
            self._handle(packet[2], packet[SHTP_HEADER_BYTES:])
        return len(packets)

    def _handle(self, channel, payload):
        if not payload:
            return
        if channel == CHANNEL_REPORTS:
            self._parse_reports(payload)
        elif channel == CHANNEL_CONTROL and payload[0] == PRODUCT_ID_RESPONSE:
            self._product_seen = True
        elif channel == CHANNEL_EXECUTABLE and payload[0] == EXECUTABLE_RESET and self._ready:
            # Enabled reports are lost after a reset; the node rebuilds the driver.
            raise OSError('BNO085 reset unexpectedly; reports must be re-enabled')

    def _parse_reports(self, payload):
        index = 0
        while index < len(payload):
            report_id = payload[index]
            if report_id in (BASE_TIMESTAMP, TIMESTAMP_REBASE):
                index += 5
                continue
            spec = SENSOR_REPORTS.get(report_id)
            # Reports are not self-delimiting: stop at an unknown ID.
            if spec is None or index + spec[0] > len(payload):
                return
            length, q_point = spec
            accuracy = payload[index + 2] & 0x03
            raw = struct.unpack_from(f'<{(length - 4) // 2}h', payload, index + 4)
            scale = 2.0 ** -q_point
            if report_id in (REPORT_ROTATION_VECTOR, REPORT_GAME_ROTATION_VECTOR):
                quaternion = tuple(v * scale for v in raw[:4])
                heading = (raw[4] * 2.0 ** -HEADING_ACCURACY_Q
                           if report_id == REPORT_ROTATION_VECTOR else math.nan)
                values = (quaternion, heading)
                if report_id == self.orientation_id:
                    self._fresh_orientation = True
            elif report_id == REPORT_MAGNETOMETER:
                values = tuple(v * scale * 1e-6 for v in raw)  # uT -> T
                self._fresh_magnetometer = True
            else:
                values = tuple(v * scale for v in raw)
            self._latest[report_id] = (values, accuracy)
            self._received_at[report_id] = time.monotonic()
            index += length
