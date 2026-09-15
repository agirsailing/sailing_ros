"""Project bow ranges onto a horizontal water plane, then fuse reference heights.

All vectors use boat FLU axes (forward, left, up). Positions are measured from
the fixed design-waterline point below the centre of mass, not from the IMU.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class HeightEstimate:
    height_m: float
    downward_cosine: float
    stamp_s: float


def beam_direction(lateral_deg, forward_deg):
    """Unit ray: positive lateral points left; positive forward points forward."""
    lateral, forward = math.radians(lateral_deg), math.radians(forward_deg)
    return (math.sin(forward),
            math.cos(forward) * math.sin(lateral),
            -math.cos(forward) * math.cos(lateral))


def vertical_row(quaternion):
    """World-up expressed in body axes: row 3 of the body-to-world rotation."""
    if not all(math.isfinite(v) for v in quaternion):
        return None
    norm = math.hypot(*quaternion)
    if norm == 0 or not math.isfinite(norm):
        return None
    x, y, z, w = (v / norm for v in quaternion)
    return (2 * (x * z - y * w),
            2 * (y * z + x * w),
            1 - 2 * (x * x + y * y))


def project_height(distance, minimum, maximum, position, beam, up, stamp,
                   min_downward_cosine):
    """Solve 0 = height + (R position).z + distance * (R beam).z."""
    if not all(math.isfinite(v) for v in
               (distance, minimum, maximum, stamp, *position, *beam, *up)):
        return None
    if not 0 <= minimum < maximum or not minimum <= distance <= maximum:
        return None
    downward = -sum(a * b for a, b in zip(up, beam))
    if downward < min_downward_cosine:
        return None
    height = distance * downward - sum(a * b for a, b in zip(up, position))
    if not math.isfinite(height):
        return None
    # Signed height: the reference may be below the local water plane.
    return HeightEstimate(height, min(1.0, downward), stamp)


def fuse_estimates(estimates, weight_power, max_disagreement_m):
    """Fuse valid, time-matched estimates. Incidence weights are a heuristic.

    On disagreement, prefer the more vertical ray. Equally credible conflicting
    readings have no unambiguous winner, so suppress the output.
    """
    if not estimates:
        return None
    heights = [item.height_m for item in estimates]
    if max(heights) - min(heights) > max_disagreement_m:
        ranked = sorted(estimates, key=lambda item: item.downward_cosine, reverse=True)
        if math.isclose(ranked[0].downward_cosine, ranked[1].downward_cosine,
                        rel_tol=1e-9, abs_tol=1e-9):
            return None
        return ranked[0].height_m
    weights = [item.downward_cosine ** weight_power for item in estimates]
    return sum(item.height_m * w for item, w in zip(estimates, weights)) / sum(weights)
