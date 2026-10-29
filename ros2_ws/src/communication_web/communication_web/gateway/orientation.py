"""Convert an already FRD/NED Imu orientation to dashboard angles, in degrees."""

import math


def dashboard_angles(imu):
    """Return roll/pitch/yaw, or None when orientation is unavailable/invalid.

    No mounting or ENU-to-NED conversion occurs here: imu_node already applied
    them. Positive roll is right side down, pitch bow up, yaw clockwise. Magnetic
    north is zero with BNO085 rotation_vector; other report modes may lack north.
    Roll is in [-180, 180], pitch in [-90, 90], and yaw in [0, 360).
    At pitch +/-90 degrees Euler roll/yaw are not independently observable;
    choose roll=0 and retain the equivalent combined rotation in yaw.
    """
    if imu.orientation_covariance[0] == -1:
        return None
    q = imu.orientation
    norm = math.hypot(q.x, q.y, q.z, q.w)
    if not math.isfinite(norm) or norm == 0:
        return None
    x, y, z, w = (v / norm for v in (q.x, q.y, q.z, q.w))
    sin_pitch = max(-1.0, min(1.0, 2.0 * (w*y - z*x)))
    pitch = math.asin(sin_pitch)
    if abs(sin_pitch) >= 1.0 - 1e-12:
        roll = 0.0
        yaw = math.atan2(2.0 * (w*z - x*y), 1.0 - 2.0 * (x*x + z*z))
    else:
        roll = math.atan2(2.0 * (w*x + y*z), 1.0 - 2.0 * (x*x + y*y))
        yaw = math.atan2(2.0 * (w*z + x*y), 1.0 - 2.0 * (y*y + z*z))
    yaw_deg = math.degrees(yaw) % 360.0
    # Floating-point modulo can round a tiny negative angle to exactly 360.
    if yaw_deg >= 360.0:
        yaw_deg = 0.0
    return math.degrees(roll), math.degrees(pitch), yaw_deg
