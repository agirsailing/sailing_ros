"""Freshness contract at expiry, missing samples and clock discontinuities."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sail_common.freshness import is_fresh


class FreshnessTests(unittest.TestCase):
    def test_ros_stamp_at_exact_expiry_and_one_nanosecond_after(self):
        # Keep integer precision even at a modern Unix epoch.
        stamp = NS(sec=1_790_000_000, nanosec=123)
        now = NS(nanoseconds=1_790_000_000_500_000_123)
        self.assertTrue(is_fresh(stamp, now, 0.5))
        now.nanoseconds += 1
        self.assertFalse(is_fresh(stamp, now, 0.5))

    def test_same_policy_for_seconds_and_ros_times(self):
        for stamp in (100.0, NS(sec=100, nanosec=0), NS(nanoseconds=100_000_000_000)):
            for now in (100.25, NS(sec=100, nanosec=250_000_000),
                        NS(nanoseconds=100_250_000_000)):
                self.assertTrue(is_fresh(stamp, now, 0.5))
                self.assertFalse(is_fresh(stamp, now, 0.1))

    def test_future_samples_and_backward_clock_are_not_fresh(self):
        self.assertFalse(is_fresh(100.0, 99.9, 0.5))
        self.assertFalse(is_fresh(NS(sec=100, nanosec=1), 100.0, 0.5))

    def test_missing_or_malformed_times_are_not_fresh(self):
        for value in (None, math.nan, math.inf, -math.inf, True, '100',
                      NS(sec=100), NS(sec=100, nanosec=-1),
                      NS(sec=100, nanosec=1_000_000_000), NS(sec=100.5, nanosec=0)):
            with self.subTest(value=value):
                self.assertFalse(is_fresh(value, 100.0, 0.5))
                self.assertFalse(is_fresh(100.0, value, 0.5))

    def test_zero_is_a_valid_simulation_timestamp(self):
        self.assertTrue(is_fresh(NS(sec=0, nanosec=0), 0.0, 0.5))
        self.assertFalse(is_fresh(NS(sec=0, nanosec=0), 1.0, 0.5))

    def test_known_mismatched_clocks_are_rejected(self):
        stamp = NS(nanoseconds=100, clock_type='ros')
        now = NS(nanoseconds=100, clock_type='steady')
        self.assertFalse(is_fresh(stamp, now, 0.5))

    def test_invalid_configuration_raises(self):
        for limit in (0, -1, math.nan, math.inf, None, True, '0.5'):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                is_fresh(100.0, 100.0, limit)

    def test_cached_sample_expires_without_another_message(self):
        stamp = NS(sec=100, nanosec=0)
        self.assertTrue(is_fresh(stamp, 100.1, 0.5))
        self.assertFalse(is_fresh(stamp, 100.6, 0.5))


if __name__ == '__main__':
    unittest.main()
