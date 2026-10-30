"""Rigid-body reference cases independent of ROS and sensor hardware."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_elaboration.processing.lever_arm import LeverArmCompensator


class LeverArmTests(unittest.TestCase):
    def test_zero_offset_preserves_first_sample_and_gravity(self):
        corrector = LeverArmCompensator((0, 0, 0), 0.2)
        self.assertEqual(corrector.update(0, (1, 2, 9.81), (3, 4, 5)), (1, 2, 9.81))

    def test_uniform_rotation_removes_centripetal_acceleration(self):
        corrector = LeverArmCompensator((2, 0, 0), 0.2)
        self.assertIsNone(corrector.update(0, (-8, 0, 9.81), (0, 0, 2)))
        self.assertEqual(corrector.update(100_000_000, (-8, 0, 9.81), (0, 0, 2)),
                         (0, 0, 9.81))

    def test_angular_acceleration_and_body_translation_on_three_axes(self):
        # r=(0,0,2), omega=(1,2,0), alpha=(2,-1,0):
        # centripetal=(0,0,-10), tangential=(-2,-4,0).
        corrector = LeverArmCompensator((0, 0, 2), 0.2)
        corrector.update(0, (0, 0, 9.81), (0.8, 2.1, 0))
        actual = corrector.update(100_000_000, (1, 0, 4.81), (1, 2, 0))
        for result, expected in zip(actual, (3, 4, 14.81)):
            self.assertAlmostEqual(result, expected)

    def test_duplicates_do_not_shift_derivative_history(self):
        corrector = LeverArmCompensator((1, 0, 0), 0.2)
        corrector.update(0, (0, 0, 0), (0, 0, 0))
        self.assertIsNone(corrector.update(0, (0, 0, 0), (0, 0, 100)))
        self.assertEqual(corrector.update(100_000_000, (-1, 10, 9.81), (0, 0, 1)),
                         (0, 0, 9.81))

    def test_invalid_sample_resets_derivative(self):
        corrector = LeverArmCompensator((1, 0, 0), 0.2)
        corrector.update(0, (0, 0, 0), (0, 0, 0))
        self.assertIsNone(corrector.update(100_000_000, (math.nan, 0, 0), (0, 0, 1)))
        self.assertIsNone(corrector.update(200_000_000, (0, 0, 0), (0, 0, 1)))


if __name__ == '__main__':
    unittest.main()
