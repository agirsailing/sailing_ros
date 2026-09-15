# Data elaboration

Processes ROS measurements without opening serial, I2C or GPIO devices.

| Node | Responsibility |
| --- | --- |
| ultrasonic_filter_node | Pair left/right samples by stamp, publish /ctrl_mean |
| imu_node | Stationary bias calibration and complementary orientation filter |
| heading_node | Select GPS course above the configured speed, otherwise compass |
| csv_logger_node | Record raw and processed topics under a timestamped CSV directory |
| battery_monitor_node | Apply the configured shutdown policy to /battery/low |

All node parameters are in config/params.yaml. Output topic names are defined
in config/endpoints.yaml and imported from data_elaboration.generated.ros_endpoints.
Input topic names are imported directly from sensors.generated.ros_endpoints:
there is no second copy of the sensor topic strings to keep synchronized.

The IMU filter retains the existing stationary, level startup assumption.
Calibration counts distinct incoming samples, then uses acquisition timestamps
for integration. Duplicate timestamps are discarded; backwards time resets the
filter. Yaw is gyro-integrated and drifts: this is not a full attitude estimator
and does not yet use the compass to correct yaw.

Heading uses fresh inputs only. /navigation/heading_deg is Float64 in degrees,
clockwise from north for GPS course. Compass axis signs/bias/offset must be
calibrated to the same convention. Without usable inputs it publishes NaN.
The original human-readable /gps String is retained as a processing output.
NAV-PVT headMot and pDOP are already scaled by pyubx2; do not divide them again.

CSV logging moved out of acquisition. It records one file per raw/processed
stream, with receipt time and acquisition time where available. This new schema
does not preserve the previous ad-hoc CSV columns; downstream exporters may
need adaptation. rosbag_manager remains independent and records ROS messages.

live_data_elaboration.launch.py starts all five nodes. The replay variant starts
processing and logging but omits battery_monitor_node so recorded alarms cannot
request shutdown. The sensors replay launch still accesses hardware for now.
data_elaboration_launch.py is the compatibility live entry point.

The live shutdown request is preserved and configured in YAML. Its effect on
the host depends on the Docker/system setup; no shutdown was executed in testing.
