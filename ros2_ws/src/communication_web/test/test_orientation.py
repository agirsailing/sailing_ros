"""Check dashboard Euler conventions, circular yaw and invalid IMU samples."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from communication_web.gateway.orientation import dashboard_angles


def imu(x=0.0, y=0.0, z=0.0, w=1.0):
    return NS(orientation=NS(x=x, y=y, z=z, w=w), orientation_covariance=[0.0] * 9)


class OrientationTests(unittest.TestCase):
    def test_cardinal_directions_and_wrap_across_north(self):
        for yaw in (0, 90, 180, 270, 359, 360, 361, -1, -90, 720, 1081):
            with self.subTest(yaw=yaw):
                half = math.radians(yaw) / 2
                angles = dashboard_angles(imu(z=math.sin(half), w=math.cos(half)))
                self.assertGreaterEqual(angles[2], 0.0)
                self.assertLess(angles[2], 360.0)
                # Compare circularly: tiny roundoff near north may yield 359.999...
                self.assertAlmostEqual(math.remainder(angles[2] - yaw, 360), 0.0)
                self.assertAlmostEqual(angles[0], 0.0)
                self.assertAlmostEqual(angles[1], 0.0)
        self.assertEqual(dashboard_angles(imu(z=-1e-20))[2], 0.0)

    def test_roll_pitch_signs_and_degrees(self):
        for angle in (-45, -20, 20, 45):
            s, c = math.sin(math.radians(angle)/2), math.cos(math.radians(angle)/2)
            self.assertAlmostEqual(dashboard_angles(imu(x=s, w=c))[0], angle)
            self.assertAlmostEqual(dashboard_angles(imu(y=s, w=c))[1], angle)

    def test_normalization_and_quaternion_sign_do_not_change_orientation(self):
        for scale in (-4, -1, 1, 7):
            result = dashboard_angles(imu(z=scale * math.sqrt(0.5),
                                          w=scale * math.sqrt(0.5)))
            self.assertAlmostEqual(result[2], 90.0)

    def test_invalid_or_unavailable_orientation_is_rejected(self):
        missing = imu()
        missing.orientation_covariance[0] = -1
        self.assertIsNone(dashboard_angles(missing))
        self.assertIsNone(dashboard_angles(imu(w=0)))
        for value in (math.nan, math.inf, -math.inf):
            for axis in ('x', 'y', 'z', 'w'):
                msg = imu()
                setattr(msg.orientation, axis, value)
                self.assertIsNone(dashboard_angles(msg))

    def test_vertical_pitch_has_a_finite_equivalent_euler_representation(self):
        for sign in (-1, 1):
            roll, pitch, yaw = dashboard_angles(imu(y=sign * math.sqrt(0.5),
                                                    w=math.sqrt(0.5)))
            self.assertEqual(roll, 0.0)
            self.assertAlmostEqual(pitch, sign * 90.0)
            self.assertAlmostEqual(yaw, 0.0)


if __name__ == '__main__':
    unittest.main()
