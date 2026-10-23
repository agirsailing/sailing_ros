# Battery hardware snapshot. Stamp is the ROS time of the GPIO low reading.
# frame_id is empty: voltage and alarm have no spatial reference frame.
std_msgs/Header header
# Latest ESP32 voltage at the GPIO read; NaN if absent or expired at publication
# according to battery_node.voltage_max_age_s (default: 5 seconds).
# This reading can predate header.stamp; it is not a synchronized measurement.
float32 voltage_v
# Raw GPIO low-battery alarm, before battery_node's shutdown confirmation.
# No message is published if this GPIO cannot be read or its cached reading
# expires; consumers must time out. Repeated publications retain header.stamp.
bool low
