"""A shared freshness policy; callers supply times from the same clock domain."""

import math
from numbers import Integral, Real


def _nanoseconds(value):
    """Accept ROS Time messages, rclpy Time objects, or numeric seconds."""
    if isinstance(value, bool):
        raise ValueError('A boolean is not a timestamp')
    if isinstance(value, Real):
        if not math.isfinite(value):
            raise ValueError('Timestamp must be finite')
        return round(value * 1_000_000_000)
    if hasattr(value, 'sec') and hasattr(value, 'nanosec'):
        if (not isinstance(value.sec, Integral) or isinstance(value.sec, bool)
                or not isinstance(value.nanosec, Integral) or isinstance(value.nanosec, bool)
                or not 0 <= value.nanosec < 1_000_000_000):
            raise ValueError('Malformed ROS timestamp')
        return value.sec * 1_000_000_000 + value.nanosec
    if hasattr(value, 'nanoseconds') and isinstance(value.nanoseconds, Integral):
        return value.nanoseconds
    raise TypeError('Expected a ROS timestamp, rclpy Time, or seconds')


def is_fresh(stamp, now, max_age_s):
    """Return whether a timestamp is no later than now and within max_age_s.

    The upper boundary is inclusive. Missing, malformed, non-finite and future
    timestamps are not fresh. Invalid limits raise ValueError (configuration
    error). Zero is a valid time, including the start of simulated time.

    Both inputs must use the SAME clock and epoch. ROS messages carry no clock
    identity: never compare ROS timestamps with time.monotonic(). Numeric inputs
    are seconds, not nanoseconds. Two rclpy Time inputs must have matching types.

    This checks age only, not measurement validity or publication frequency.
    Call again before reusing cached data; it does not schedule expiry callbacks.
    """
    if (isinstance(max_age_s, bool) or not isinstance(max_age_s, Real)
            or not math.isfinite(max_age_s) or max_age_s <= 0):
        raise ValueError('max_age_s must be finite and positive')
    if (hasattr(stamp, 'clock_type') and hasattr(now, 'clock_type')
            and stamp.clock_type != now.clock_type):
        return False
    try:
        age_ns = _nanoseconds(now) - _nanoseconds(stamp)
    except (TypeError, ValueError, OverflowError):
        return False
    return 0 <= age_ns <= round(max_age_s * 1_000_000_000)
