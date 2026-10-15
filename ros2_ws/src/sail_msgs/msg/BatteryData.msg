# Battery hardware snapshot. Stamp is the ROS time of the GPIO low reading.
# frame_id is empty: voltage and alarm have no spatial reference frame.
std_msgs/Header header
# Latest ESP32 voltage in volts; NaN if absent or older than 5 seconds.
# This reading can predate header.stamp; it is not a synchronized measurement.
float32 voltage_v
# Raw GPIO low-battery alarm, before battery_node's shutdown confirmation.
# No message is published if this GPIO cannot be read; consumers must time out.
bool low
