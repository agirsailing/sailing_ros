"""BNO085 acquisition over SHTP/I2C: fused orientation plus 9-DOF measurements.

The sensor runs CEVA (Hillcrest) SH-2 firmware. The host enables reports at a
chosen interval and the sensor streams them; this driver only frames SHTP
packets and decodes the reports it enabled. No filtering or frame conversion
happens here.

Axes are the breakout's printed X/Y/Z. The rotation vector is the body
orientation relative to an East-North-Up world referenced to MAGNETIC north
and gravity (not true north). The game rotation vector has no heading
reference: roll/pitch are gravity-referenced, yaw is relative and drifts.

"""

from dataclasses import dataclass
import math
import struct
import time

from smbus2 import i2c_msg

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


@dataclass(frozen=True)
class ImuSample:
    orientation: tuple            # (x, y, z, w): body -> world quaternion
    orientation_accuracy: int     # SH-2 status: 0 unreliable .. 3 high
    heading_accuracy_rad: float   # NaN for the game rotation vector
    acceleration: tuple           # m/s^2, gravity included
    angular_velocity: tuple       # rad/s
    magnetic_field: tuple         # tesla; None unless a new report arrived
    magnetic_accuracy: int        # SH-2 status; -1 before the first report


class ImuDriver:
    def __init__(self, mux, channel, address, report_interval_s,
                 magnetometer_interval_s, orientation_report='rotation_vector',
                 reset_delay_s=0.5, response_timeout_s=1.0,
                 stale_timeout_s=1.0, max_packets_per_read=16):
        if orientation_report not in ORIENTATION_REPORTS:
            raise ValueError(f'Unknown orientation report: {orientation_report}')
        if not report_interval_s > 0 or not magnetometer_interval_s > 0:
            raise ValueError('Report intervals must be positive')
        self.mux, self.channel, self.address = mux, channel, address
        self.orientation_id = ORIENTATION_REPORTS[orientation_report]
        self.stale_timeout_s = stale_timeout_s
        self.max_packets = max_packets_per_read
        self._sequence = [0] * CHANNEL_COUNT
        self._latest = {}            # report ID -> (values, accuracy)
        self._fresh_orientation = False
        self._fresh_magnetometer = False
        self._product_seen = False
        self._ready = False

        # Soft reset, then drain the advertisement and reset-complete packets.
        with self._access() as bus:
            self._write(bus, CHANNEL_EXECUTABLE, [EXECUTABLE_RESET])
        time.sleep(reset_delay_s)
        with self._access() as bus:
            while self._poll(bus):
                pass

        # Confirm an SH-2 device answers before enabling reports.
        with self._access() as bus:
            self._write(bus, CHANNEL_CONTROL, [PRODUCT_ID_REQUEST, 0])
        deadline = time.monotonic() + response_timeout_s
        while not self._product_seen:
            if time.monotonic() > deadline:
                raise OSError('No SH-2 product ID response; check address, wiring '
                              'and whether the device is a BNO08x')
            time.sleep(0.01)
            with self._access() as bus:
                self._poll(bus)

        with self._access() as bus:
            for report_id, interval in (
                    (self.orientation_id, report_interval_s),
                    (REPORT_ACCELEROMETER, report_interval_s),
                    (REPORT_GYROSCOPE, report_interval_s),
                    (REPORT_MAGNETOMETER, magnetometer_interval_s)):
                self._write(bus, CHANNEL_CONTROL, struct.pack(
                    '<BBBHIII', SET_FEATURE_COMMAND, report_id, 0, 0,
                    int(round(interval * 1e6)), 0, 0))
        self._ready = True
        self._last_packet_s = time.monotonic()

    # -----------------------
    #   Public API
    # -----------------------
    def read(self):
        """Process queued packets; return a sample when a new orientation arrived."""
        now = time.monotonic()
        with self._access() as bus:
            count = self._poll(bus)
        if count:
            self._last_packet_s = now
        elif now - self._last_packet_s > self.stale_timeout_s:
            raise OSError('BNO085 stopped reporting')
        required = (self.orientation_id, REPORT_ACCELEROMETER, REPORT_GYROSCOPE)
        if not self._fresh_orientation or any(r not in self._latest for r in required):
            return None
        self._fresh_orientation = False
        (quaternion, heading_accuracy), orientation_accuracy = self._latest[self.orientation_id]
        magnetic_field, magnetic_accuracy = None, -1
        if REPORT_MAGNETOMETER in self._latest:
            values, magnetic_accuracy = self._latest[REPORT_MAGNETOMETER]
            if self._fresh_magnetometer:
                magnetic_field = values
                self._fresh_magnetometer = False
        return ImuSample(
            orientation=quaternion,
            orientation_accuracy=orientation_accuracy,
            heading_accuracy_rad=heading_accuracy,
            acceleration=self._latest[REPORT_ACCELEROMETER][0],
            angular_velocity=self._latest[REPORT_GYROSCOPE][0],
            magnetic_field=magnetic_field,
            magnetic_accuracy=magnetic_accuracy)

    # -----------------------
    #   Transport
    # -----------------------
    def _access(self):
        # Hold the mux lock for the whole transaction, as the other drivers do.
        if self.channel < 0:
            return self.mux.upstream()
        return self.mux.channel(self.channel)

    def _i2c_read(self, bus, length):
        msg = i2c_msg.read(self.address, length)
        bus.i2c_rdwr(msg)
        return bytes(msg)

    def _write(self, bus, channel, payload):
        payload = bytes(payload)
        length = len(payload) + SHTP_HEADER_BYTES
        sequence = self._sequence[channel]
        self._sequence[channel] = (sequence + 1) & 0xFF
        header = bytes([length & 0xFF, length >> 8, channel, sequence])
        bus.i2c_rdwr(i2c_msg.write(self.address, header + payload))

    def _read_packet(self, bus):
        # Every I2C read starts with the SHTP header: read it, then the packet.
        header = self._i2c_read(bus, SHTP_HEADER_BYTES)
        length = (header[0] | header[1] << 8) & 0x7FFF
        if length < SHTP_HEADER_BYTES:
            return None
        if length > MAX_PACKET_BYTES:
            raise OSError(f'Invalid SHTP packet length: {length}')
        data = self._i2c_read(bus, length)
        return data[2], data[SHTP_HEADER_BYTES:length]

    def _poll(self, bus):
        count = 0
        for _ in range(self.max_packets):
            packet = self._read_packet(bus)
            if packet is None:
                break
            self._handle(*packet)
            count += 1
        return count

    # -----------------------
    #   SH-2 decoding
    # -----------------------
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
            index += length
