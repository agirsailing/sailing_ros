"""Receive the battery voltage from the ESP32 (100 baud, 8N1, idle high).

Packet: [decivolts][~decivolts], both LSB first. Bits are rebuilt from the
kernel's edge timestamps, so Python timing jitter does not matter.
"""

import lgpio

BIT_NS = 10_000_000  # 10 ms per bit
WATCHDOG = 2         # lgpio reports "no edge for a while" as level 2
PACKET_NS = 20 * BIT_NS
# Longer than the longest constant level within an 8N1 frame (9 bits).
IDLE_MICROS = 110_000

class BatteryDriver:
    def __init__(self, chip, line):
        self.chip, self.line = chip, line
        self.edges = []
        self.latest = None  # (volts, packet end in CLOCK_MONOTONIC seconds)
        self._closed = False
        lgpio.gpio_claim_alert(chip, line, lgpio.BOTH_EDGES, lgpio.SET_PULL_UP)
        self.cb = None
        try:
            self.cb = lgpio.callback(chip, line, lgpio.BOTH_EDGES, self._on_edge)
            lgpio.gpio_set_watchdog_micros(chip, line, IDLE_MICROS)
        except Exception:
            self.close()
            raise

    def _on_edge(self, chip, line, level, timestamp):
        if self._closed:
            return
        # Decode at idle, even if this is the last packet ever received.
        # Watchdog and edge callbacks are delivered by the same lgpio thread.
        if self.edges and timestamp - self.edges[0][0] >= PACKET_NS:
            self._decode()
            self.edges = []
        if level == WATCHDOG:
            self.edges = []  # Discard incomplete packets as well.
            return
        if self.edges or level == 0:  # a falling edge starts a packet
            self.edges.append((timestamp, level))

    def _level_at(self, t):
        level = 1
        for timestamp, edge_level in self.edges:
            if timestamp > t:
                break
            level = edge_level
        return level

    def _decode(self):
        t0 = self.edges[0][0]
        values = []
        for frame in range(2):
            # Sample each of the 10 bits in its middle.
            bits = [self._level_at(t0 + (frame * 10 + k + 0.5) * BIT_NS)
                    for k in range(10)]
            if bits[0] != 0 or bits[9] != 1:  # bad start or stop bit
                return
            values.append(sum(bit << i for i, bit in enumerate(bits[1:9])))
        if values[0] ^ values[1] == 0xFF:  # second byte must be the inverse
            # Linux GPIO v2 timestamps use CLOCK_MONOTONIC by default, the
            # same clock battery_node uses for voltage expiry. Decoding later
            # must not give an old packet a new acquisition time.
            self.latest = (values[0] / 10.0, (t0 + PACKET_NS) / 1e9)

    def close(self):
        if not self._closed:
            self._closed = True
            if self.cb is not None:
                self.cb.cancel()
            lgpio.gpio_free(self.chip, self.line)
