"""Receive the battery voltage from the ESP32 (100 baud, 8N1, idle high).

Packet: [decivolts][~decivolts], both LSB first. Bits are rebuilt from the
kernel's edge timestamps, so Python timing jitter does not matter.
"""

import time
import lgpio

BIT_NS = 10_000_000  # 10 ms per bit
WATCHDOG = 2         # lgpio reports "no edge for a while" as level 2

class BatteryDriver:
    def __init__(self, chip, line):
        self.chip, self.line = chip, line
        self.edges = []
        self.latest = None  # (volts, time received)
        lgpio.gpio_claim_alert(chip, line, lgpio.BOTH_EDGES, lgpio.SET_PULL_UP)
        self.cb = lgpio.callback(chip, line, lgpio.BOTH_EDGES, self._on_edge)

    def _on_edge(self, chip, line, level, timestamp):
        if level == WATCHDOG:
            return
        # A packet lasts 20 bits; an edge after that belongs to the next one.
        if self.edges and timestamp - self.edges[0][0] > 20 * BIT_NS:
            self._decode()
            self.edges = []
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
            self.latest = (values[0] / 10.0, time.monotonic())

    def close(self):
        self.cb.cancel()
        lgpio.gpio_free(self.chip, self.line)