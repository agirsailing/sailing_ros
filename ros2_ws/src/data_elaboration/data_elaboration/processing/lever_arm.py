"""Transfer rigid-body specific force from the IMU to the body origin.

All vectors are already expressed in body FLU axes. The offset points from
the body origin (COM) to the sensor, in metres. Gravity is preserved.
"""

import math


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


class LeverArmCompensator:
    def __init__(self, offset, max_dt_s):
        if len(offset) != 3 or not all(math.isfinite(v) for v in offset):
            raise ValueError('Lever arm must contain three finite distances')
        if not math.isfinite(max_dt_s) or max_dt_s <= 0:
            raise ValueError('max_dt_s must be finite and positive')
        self.offset = tuple(offset)
        self.enabled = any(v != 0 for v in self.offset)
        self.max_dt_ns = round(max_dt_s * 1_000_000_000)
        self.reset()

    def reset(self):
        self.previous = None

    def update(self, stamp_ns, acceleration, omega):
        """Return corrected acceleration, or None until a derivative is available.

        Use distinct source timestamps, never publication timer intervals.
        Finite differences approximate angular acceleration at the current sample.
        Re-seed after a clock reset or long gap; ignore duplicate timestamps.
        """
        if (len(acceleration) != 3 or len(omega) != 3
                or not all(math.isfinite(v) for v in (*acceleration, *omega))):
            self.reset()
            return None
        if not self.enabled:
            return tuple(acceleration)
        previous = self.previous
        if previous is not None and stamp_ns == previous[0]:
            return None
        self.previous = (stamp_ns, tuple(omega))
        if previous is None:
            return None
        dt_ns = stamp_ns - previous[0]
        if dt_ns <= 0 or dt_ns > self.max_dt_ns:
            return None
        dt = dt_ns / 1_000_000_000
        alpha = tuple((current - old) / dt for current, old in zip(omega, previous[1]))
        tangential = cross(alpha, self.offset)
        centripetal = cross(omega, cross(omega, self.offset))
        corrected = tuple(a - t - c for a, t, c in zip(acceleration, tangential, centripetal))
        if not all(math.isfinite(v) for v in corrected):
            self.reset()
            return None
        return corrected
