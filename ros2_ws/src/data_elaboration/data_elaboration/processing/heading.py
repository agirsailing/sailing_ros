"""Select receiver course or magnetic heading using fresh measurements."""

import math


def choose_heading(gps, compass, now, max_age, speed_threshold,
                   x_sign, y_sign, x_bias, y_bias, offset_deg):
    if gps is not None:
        stamp, valid, speed, course = gps
        if (0 <= now - stamp <= max_age and valid
                and math.isfinite(speed) and math.isfinite(course)
                and speed > speed_threshold):
            return course % 360.0
    if compass is not None:
        stamp, x, y = compass
        if 0 <= now - stamp <= max_age and math.isfinite(x) and math.isfinite(y):
            x, y = x_sign * (x - x_bias), y_sign * (y - y_bias)
            if x != 0 or y != 0:
                return (math.degrees(math.atan2(y, x)) + offset_deg) % 360.0
    return float('nan')
