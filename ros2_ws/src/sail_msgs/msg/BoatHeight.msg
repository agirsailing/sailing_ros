# Signed vertical clearance of the boat-fixed design-waterline reference
# below the centre of mass, relative to the locally horizontal water surface.
# Estimated from left/right slant ranges, mounting geometry and IMU attitude.
# Positive above water, negative below. Height is world-vertical, not body-Z.
# Header frame identifies the boat reference; no TF is created by this message.
# Stamp belongs to the triggering range; a paired range may differ by max_pair_dt_s.
std_msgs/Header header
float64 height_m
