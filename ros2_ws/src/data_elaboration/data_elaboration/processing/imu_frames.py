"""Quaternion helpers for static TF and the remaining world-reference change."""

import math


def multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quaternion_from_degrees(roll, pitch, yaw):
    r, p, y = (math.radians(v) / 2 for v in (roll, pitch, yaw))
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def rotation_matrix(q):
    norm = math.hypot(*q)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('Invalid rotation quaternion')
    x, y, z, w = (v / norm for v in q)
    return ((1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)),
            (2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)),
            (2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)))


def rotate_covariance(matrix, covariance):
    if covariance[0] == -1:
        return list(covariance)
    return [sum(matrix[i][k] * covariance[3*k + l] * matrix[j][l]
                for k in range(3) for l in range(3))
            for i in range(3) for j in range(3)]
