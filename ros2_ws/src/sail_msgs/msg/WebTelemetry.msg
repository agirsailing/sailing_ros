# Snapshot for the web dashboard. Header stamp is snapshot time (ROS clock).
# Angles use aerospace axes: right side down / bow up / turn right positive.
# Yaw is relative to IMU initialization, not north. Invalid numbers are NaN.
std_msgs/Header header
bool attitude_valid
float64 roll_deg
float64 pitch_deg
float64 yaw_deg
bool height_valid
float64 height_m
# The hardware only reports a low-battery alarm, not charge percentage.
bool battery_valid
bool battery_low
bool sog_valid
float64 sog_mps
