"""Offline geometry checks with synthetic rays intersecting a water plane."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_elaboration.processing.boat_height import (
    HeightEstimate, beam_direction, fuse_estimates, project_height, vertical_row,
)


def rotation(roll, pitch, yaw):
    """Independent full Rz Ry Rx matrix for synthetic sensor measurements."""
    r, p, y = map(math.radians, (roll, pitch, yaw))
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp, cp * sr, cp * cr))


def quaternion(roll, pitch, yaw):
    r, p, y = (math.radians(v) / 2 for v in (roll, pitch, yaw))
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


class BoatHeightTests(unittest.TestCase):
    def test_projection_recovers_height_with_roll_pitch_yaw_and_mount_offsets(self):
        for roll in (-35, -15, 0, 15, 35):
            for pitch in (-12, 0, 12):
                for yaw in (0, 80, 230):
                    for lateral in (-15, 15):
                        with self.subTest(roll=roll, pitch=pitch, yaw=yaw, lateral=lateral):
                            position = (1.8, 0.12 if lateral > 0 else -0.12, 0.45)
                            beam = beam_direction(lateral, 3)
                            row = rotation(roll, pitch, yaw)[2]
                            origin_z = 0.8 + sum(a * b for a, b in zip(row, position))
                            ray_z = sum(a * b for a, b in zip(row, beam))
                            distance = -origin_z / ray_z
                            up = vertical_row(quaternion(roll, pitch, yaw))
                            result = project_height(distance, 0, 20, position, beam, up, 1, 0.3)
                            self.assertIsNotNone(result)
                            self.assertAlmostEqual(result.height_m, 0.8)

    def test_level_geometry_subtracts_mount_height_after_slant_correction(self):
        result = project_height(2, 0, 4.5, (2, 0, 0.4), beam_direction(15, 0),
                                (0, 0, 1), 1, 0.5)
        self.assertAlmostEqual(result.height_m, 2 * math.cos(math.radians(15)) - 0.4)

    def test_signed_height_allows_submerged_reference(self):
        result = project_height(0.5, 0, 4.5, (0, 0, 0.8), (0, 0, -1),
                                (0, 0, 1), 1, 0.5)
        self.assertAlmostEqual(result.height_m, -0.3)

    def test_roll_favours_correct_side_and_flat_weights_are_equal(self):
        for roll, preferred in ((-15, 0), (0, None), (15, 1)):
            up = vertical_row(quaternion(roll, 0, 0))
            estimates = [project_height(1, 0, 4.5, (0, 0, 0), beam_direction(a, 0),
                                        up, 1, 0.5) for a in (15, -15)]
            if preferred is not None:
                self.assertAlmostEqual(estimates[preferred].downward_cosine, 1)
                self.assertGreater(estimates[preferred].downward_cosine,
                                   estimates[1 - preferred].downward_cosine)
            # Different hypothetical heights expose the actual weight ratio.
            pair = [HeightEstimate(1 + i * 0.1, item.downward_cosine, 1)
                    for i, item in enumerate(estimates)]
            h = fuse_estimates(pair, 8, 0.25)
            if preferred == 0:
                self.assertLess(h, 1.05)
            elif preferred == 1:
                self.assertGreater(h, 1.05)
            else:
                self.assertAlmostEqual(h, 1.05)

    def test_invalid_ranges_upward_rays_and_bad_quaternions_are_rejected(self):
        for distance in (float('nan'), float('inf'), -1, 5):
            self.assertIsNone(project_height(distance, 0, 4.5, (0, 0, 0),
                                            (0, 0, -1), (0, 0, 1), 1, 0.5))
        for beam in ((0, 0, 1), (1, 0, 0), beam_direction(80, 0)):
            self.assertIsNone(project_height(1, 0, 4.5, (0, 0, 0), beam,
                                            (0, 0, 1), 1, 0.5))
        for q in ((0, 0, 0, 0), (0, 0, float('nan'), 1), (0, 0, 0, float('inf'))):
            self.assertIsNone(vertical_row(q))
        self.assertEqual(vertical_row((0, 0, 0, 2)), (0, 0, 1))

    def test_single_sensor_disagreement_and_ambiguous_ties(self):
        a, b = HeightEstimate(1, 1, 1), HeightEstimate(2, 0.8, 1)
        self.assertEqual(fuse_estimates([a], 8, 0.25), 1)
        self.assertEqual(fuse_estimates([a, b], 8, 0.25), 1)
        self.assertIsNone(fuse_estimates([a, HeightEstimate(2, 1, 1)], 8, 0.25))
        self.assertIsNone(fuse_estimates([], 8, 0.25))


if __name__ == '__main__':
    unittest.main()
