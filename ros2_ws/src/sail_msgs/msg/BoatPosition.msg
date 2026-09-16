# Snapshot time and original GPS sample time, respectively (ROS clock).
std_msgs/Header header
builtin_interfaces/Time gps_stamp
# False when position/speed are missing, invalid or stale; numbers then are NaN.
bool fix_valid
float64 latitude_deg
float64 longitude_deg
float64 sog_mps
