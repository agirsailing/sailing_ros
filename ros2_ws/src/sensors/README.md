# Sensors

Nodes acquire hardware measurements. battery_node also owns the low-battery
shutdown policy; calibration, filtering and heading selection belong to data_elaboration.

## Configuration and endpoints

- config/params.yaml: all deployment parameters for nodes in this package.
  Missing parameters fail explicitly; there are no hidden hardware defaults.
- config/endpoints.yaml: the only source for sensor topic names.
- sensors/generated/ros_endpoints.py: generator output imported by publishers
  and by downstream packages. build.sh regenerates it before colcon.
- Register addresses, protocol frames and SI unit conversions remain in drivers:
  they define the protocol rather than the installation configuration.
- The left/right bow sensors select generated endpoint groups from YAML.
  Both are enabled. Set enabled: false for an absent sensor; the height estimator
  can use a single valid sensor. Full Pi setup installs stable udev names tied
  to physical USB ports: left=1.4, right=1.3, GPS=1.2. Keep cables in these ports.
  Beam angles and mounting positions belong
  to data_elaboration/config/params.yaml; acquisition publishes slant ranges.

## Acquisition

| Node | Interface | Message / topic |
| --- | --- | --- |
| ultrasonic_left_node | /dev/ultrasonic_left | sensor_msgs/Range /ultrasonic/left (m) |
| ultrasonic_right_node | /dev/ultrasonic_right | sensor_msgs/Range /ultrasonic/right (m) |
| gps_node | /dev/gps, NAV-PVT | sail_msgs/GpsData /gps/data |
| i2c_sensors_node | bus 1, mux 0x70, channel 2 | sensor_msgs/Imu /imu/data |
| i2c_sensors_node | same mux, channel 0 | geometry_msgs/Vector3Stamped /compass/data |
| battery_node | gpiochip0 line 13 (alarm), line 6 (ESP32 voltage link) | sail_msgs/BatteryData /battery/data |

BatteryData contains only `header`, `voltage_v` (volts) and `low` (raw GPIO alarm).
`header.stamp` is the ROS time of the GPIO reading; `header.frame_id` stays empty
because these scalars have no spatial frame. Voltage is the latest ESP32 reading,
not necessarily acquired at that timestamp; absent or older-than-5-second voltage
is NaN. A GPIO read failure suppresses the entire snapshot, so consumers must
expire missing messages rather than treating a missing alarm as false.
There are no per-field validity booleans and no charge-percentage estimate.
The separate `/battery/voltage` publisher has been removed.

battery_node also counts consecutive `low=true` samples and, once the configured
threshold is reached, requests shutdown at most once per node execution.
`BatteryData.low` remains the raw GPIO alarm, not the confirmation result.
In config/params.yaml, `shutdown_enabled` defaults to true,
`low_samples_required` to 1 and `shutdown_command` to `[sudo, shutdown, "-h", now]`.
A valid `low=false` sample clears the counter. Missing voltage does not suppress
a GPIO alarm or the shutdown request. GPIO read errors produce no new sample
and do not advance the counter. A failed shutdown command is logged, without
repeated execution on every sample. Its effect on the host depends on Docker.
There is no separate monitoring node or `/processed/battery/low` topic.

Compass values are signed raw counts, not tesla: the exact model and sensitivity
still need hardware confirmation. IMU acceleration is m/s^2 and gyro is rad/s.
Raw IMU orientation is absent (orientation_covariance[0] = -1); the measured
vectors have zero covariances to indicate unknown uncertainty.

The mux owner holds a lock across channel selection, sensor access and
deselection, including failures. The lock protects only this process; do not
launch another program that manually operates this mux. A failed sensor is
retried independently. Compass conversion currently holds the bus for 20 ms:
the configured 50 Hz IMU rate is nominal and can jitter. Processing uses message
timestamps, not an assumed fixed interval. A kernel mux driver or asynchronous
conversion scheduling may be considered after hardware timing measurements.

## Launch

live_sensors.launch.py and replay_sensors.launch.py both start all acquisition
nodes, including IMU via i2c_sensors_node. Replay explicitly overrides
`shutdown_enabled=false` for battery_node after loading the shared YAML.
sensors_launch.py is a compatibility entry point with the same acquisition set.
Replay is not yet a hardware-free bag pipeline. Do not start both modes together.

Both launch files accept sensors_params_file to override the installed YAML.
The orchestrator now includes sensors and data_elaboration for each mode.

## Hardware checks still required

USB enumeration, actual wiring, GPIO permissions, mux model/channel count and
magnetometer register protocol have not been verified on the Raspberry.
No Docker commands or ROS/hardware execution were used during the refactor.

## References

- pyubx2 NAV-PVT field scaling:
  https://github.com/semuconsulting/pyubx2/blob/master/src/pyubx2/ubxtypes_get.py
- LSM6DS3TR-C register settings and sensitivities:
  https://www.st.com/resource/en/datasheet/lsm6ds3tr-c.pdf
- ROS Imu covariance conventions:
  https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/Imu.msg
