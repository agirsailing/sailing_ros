"""Serialize complete select/access/deselect transactions in one process."""

from contextlib import contextmanager
from threading import RLock


class I2CMultiplexer:
    def __init__(self, bus, address, channel_count):
        self.bus = bus
        self.address = address
        self.channel_count = channel_count
        self._lock = RLock()

    @contextmanager
    def channel(self, channel):
        if not 0 <= channel < self.channel_count:
            raise ValueError(f'Invalid multiplexer channel: {channel}')
        with self._lock:
            try:
                self.bus.write_byte(self.address, 1 << channel)
                yield self.bus
            finally:
                self.bus.write_byte(self.address, 0)

    def close(self):
        with self._lock:
            try:
                self.bus.write_byte(self.address, 0)
            finally:
                self.bus.close()
