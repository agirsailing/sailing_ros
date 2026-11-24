"""Replay timestamped GPIO edges without hardware or real-time sleeps."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class BatteryDriverTests(unittest.TestCase):
    def setUp(self):
        self.gpio = Mock(BOTH_EDGES=3, SET_PULL_UP=32)
        path = Path(__file__).resolve().parents[1] / 'sensors/drivers/battery_driver.py'
        spec = importlib.util.spec_from_file_location('tested_battery_driver', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, lgpio=self.gpio):
            spec.loader.exec_module(self.module)
        self.driver = self.module.BatteryDriver(0, 6)
        self.addCleanup(self.driver.close)

    def packet(self, value, start=100_000_000_000, inverse=None):
        previous = 1
        second = value ^ 255 if inverse is None else inverse
        bits = []
        for byte in (value, second):
            bits.extend([0] + [(byte >> bit) & 1 for bit in range(8)] + [1])
        last = start
        for index, level in enumerate(bits):
            if level != previous:
                last = start + index * self.module.BIT_NS
                self.driver._on_edge(0, 6, level, last)
            previous = level
        return last

    def test_final_packet_decodes_on_idle_without_another_packet(self):
        last = self.packet(124)
        self.assertIsNone(self.driver.latest)
        self.driver._on_edge(0, 6, 2, last + 110_000_000)
        self.assertEqual(self.driver.latest, (12.4, 100.2))
        self.gpio.gpio_set_watchdog_micros.assert_called_once_with(0, 6, 110_000)

    def test_every_voltage_decodes_including_long_constant_levels(self):
        for value in range(256):
            self.driver.edges = []
            self.driver.latest = None
            last = self.packet(value)
            self.driver._on_edge(0, 6, 2, last + 110_000_000)
            self.assertEqual(self.driver.latest, (value / 10, 100.2))

    def test_delayed_callback_never_refreshes_old_packet_timestamp(self):
        self.packet(124)
        self.driver._on_edge(0, 6, 0, 110_000_000_000)
        self.assertEqual(self.driver.latest, (12.4, 100.2))

    def test_back_to_back_packets_split_at_exact_boundary(self):
        self.packet(124)
        last = self.packet(120, start=100_200_000_000)
        self.assertEqual(self.driver.latest, (12.4, 100.2))
        self.driver._on_edge(0, 6, 2, last + 110_000_000)
        self.assertEqual(self.driver.latest, (12.0, 100.4))

    def test_invalid_or_incomplete_packet_does_not_refresh_last_value(self):
        last = self.packet(124)
        self.driver._on_edge(0, 6, 2, last + 110_000_000)
        last = self.packet(120, start=101_000_000_000, inverse=120)
        self.driver._on_edge(0, 6, 2, last + 110_000_000)
        self.driver._on_edge(0, 6, 0, 102_000_000_000)
        self.driver._on_edge(0, 6, 2, 102_110_000_000)
        self.assertEqual(self.driver.latest, (12.4, 100.2))
        self.assertEqual(self.driver.edges, [])

    def test_close_cancels_callback_and_late_events_are_ignored(self):
        self.packet(124)
        self.driver.close()
        self.driver.close()
        self.driver._on_edge(0, 6, 2, 101_000_000_000)
        self.assertIsNone(self.driver.latest)
        self.gpio.callback.return_value.cancel.assert_called_once()
        self.gpio.gpio_free.assert_called_once_with(0, 6)

    def test_watchdog_setup_failure_releases_gpio(self):
        self.driver.close()
        self.gpio.reset_mock()
        self.gpio.gpio_set_watchdog_micros.side_effect = RuntimeError('watchdog failed')
        with self.assertRaisesRegex(RuntimeError, 'watchdog failed'):
            self.module.BatteryDriver(0, 6)
        self.gpio.callback.return_value.cancel.assert_called_once()
        self.gpio.gpio_free.assert_called_once_with(0, 6)


if __name__ == '__main__':
    unittest.main()
