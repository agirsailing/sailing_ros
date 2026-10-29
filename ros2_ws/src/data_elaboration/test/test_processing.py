"""Offline processing regression tests, using recorded-style timestamps."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'sail_common'))
from data_elaboration.processing.imu_filter import ImuFilter


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



if __name__ == '__main__':
    unittest.main()
