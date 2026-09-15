"""Offline processing regression tests, using recorded-style timestamps."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_elaboration.processing.imu_filter import ImuFilter
from data_elaboration.processing.heading import choose_heading


class ProcessingTests(unittest.TestCase):
    def test_imu_calibration_uses_distinct_samples_and_preserves_gravity(self):
        filt = ImuFilter(2, 9.80665, 0.98, 0.2)
        accel, gyro = (0.1, 0.2, 10.00665), (0.01, 0.02, 0.03)
        self.assertIsNone(filt.update(1.0, accel, gyro))
        self.assertIsNone(filt.update(1.0, accel, gyro))
        self.assertEqual(filt.count, 1)
        self.assertIsNone(filt.update(1.02, accel, gyro))
        a, g, q = filt.update(1.04, accel, gyro)
        self.assertAlmostEqual(a[2], 9.80665)
        self.assertEqual(g, (0.0, 0.0, 0.0))
        self.assertEqual(q, (0.0, 0.0, 0.0, 1.0))

    def test_imu_integrates_actual_dt_and_resets_on_backwards_time(self):
        filt = ImuFilter(0, 9.80665, 0.98, 0.2)
        filt.update(1.0, (0, 0, 9.80665), (0, 0, 1))
        filt.update(1.1, (0, 0, 9.80665), (0, 0, 1))
        self.assertAlmostEqual(filt.yaw, 0.1)
        filt.update(2.0, (0, 0, 9.80665), (0, 0, 1))
        self.assertAlmostEqual(filt.yaw, 0.1)  # No integration across the gap.
        filt.update(0.0, (0, 0, 9.80665), (0, 0, 1))
        self.assertEqual(filt.yaw, 0)

    def test_heading_selects_course_or_compass_and_rejects_stale_data(self):
        args = (10.0, 1.0, 0.5, 1.0, 1.0, 0.0, 0.0, 0.0)
        compass = (9.9, 0.0, 100.0)
        self.assertEqual(choose_heading((9.9, True, 1.0, 270), compass, *args), 270)
        self.assertEqual(choose_heading((9.9, True, 0.1, 270), compass, *args), 90)
        self.assertEqual(choose_heading((9.9, False, 1.0, 270), compass, *args), 90)
        self.assertTrue(math.isnan(choose_heading((8.0, True, 1.0, 270),
                                                  (8.0, 0.0, 100.0), *args)))
        self.assertTrue(math.isnan(choose_heading(None, (9.9, 0.0, 0.0), *args)))


if __name__ == '__main__':
    unittest.main()
