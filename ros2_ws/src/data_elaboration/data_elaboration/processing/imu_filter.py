"""Stationary bias calibration and the existing complementary filter."""

import math


class ImuFilter:
    def __init__(self, calibration_samples, gravity, alpha, max_dt):
        if calibration_samples < 0 or not 0 <= alpha <= 1:
            raise ValueError('Invalid IMU calibration/filter configuration')
        self.samples = calibration_samples
        self.gravity, self.alpha, self.max_dt = gravity, alpha, max_dt
        self.reset()

    def reset(self):
        self.count = 0
        self.sums = [0.0] * 6
        self.offsets = [0.0] * 6
        self.last_stamp = None
        self.roll = self.pitch = self.yaw = 0.0
        self.initialized = False

    def update(self, stamp, acceleration, angular_velocity):
        values = tuple(acceleration) + tuple(angular_velocity)
        if not all(math.isfinite(v) for v in (stamp, *values)):
            return None
        if self.last_stamp is not None:
            if stamp == self.last_stamp:
                return None
            if stamp < self.last_stamp:
                # Bag loops / clock resets must not integrate a negative dt.
                self.reset()
        previous = self.last_stamp
        self.last_stamp = stamp
        if self.count < self.samples:
            self.sums = [a + b for a, b in zip(self.sums, values)]
            self.count += 1
            if self.count == self.samples:
                self.offsets = [v / self.samples for v in self.sums]
                self.offsets[2] -= self.gravity
            return None
        ax, ay, az, gx, gy, gz = [v - bias for v, bias in zip(values, self.offsets)]
        accel_roll = math.atan2(ay, az)
        accel_pitch = math.atan2(-ax, math.hypot(ay, az))
        dt = None if previous is None else stamp - previous
        if not self.initialized or dt is None or dt > self.max_dt:
            self.roll, self.pitch = accel_roll, accel_pitch
            self.initialized = True
        else:
            self.roll = self.alpha * (self.roll + gx * dt) + (1 - self.alpha) * accel_roll
            self.pitch = self.alpha * (self.pitch + gy * dt) + (1 - self.alpha) * accel_pitch
            self.yaw += gz * dt
        cr, sr = math.cos(self.roll / 2), math.sin(self.roll / 2)
        cp, sp = math.cos(self.pitch / 2), math.sin(self.pitch / 2)
        cy, sy = math.cos(self.yaw / 2), math.sin(self.yaw / 2)
        quaternion = (sr * cp * cy - cr * sp * sy,
                      cr * sp * cy + sr * cp * sy,
                      cr * cp * sy - sr * sp * cy,
                      cr * cp * cy + sr * sp * sy)
        return (ax, ay, az), (gx, gy, gz), quaternion
