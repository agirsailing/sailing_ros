# Estimated fixed-axis roll/pitch/yaw in degrees, matching the companion Imu attitude.
# Companion sensor_msgs/Imu outputs retain quaternions and SI angular velocity.
# The topic selects the convention:
# /processed/imu/rpy: FLU body and a local up-world reference.
# /processed/imu/rpy/aero: FRD body and a local down-world reference.
# Both are zero at a level startup; yaw is continuous and relative to startup.
# No geographic north reference; gyro integration can drift.
std_msgs/Header header
float64 roll_deg
float64 pitch_deg
float64 yaw_deg
