# Receiver NAV-PVT solution, without compass fusion or application filtering.
# Header stamp is ROS acquisition time (also used during replay).
std_msgs/Header header
float64 latitude_deg
float64 longitude_deg
float64 altitude_msl_m
float64 ground_speed_mps
float64 course_deg
float64 position_dop
float64 horizontal_accuracy_m
float64 vertical_accuracy_m
uint8 satellites_used
uint8 fix_type
bool fix_valid
