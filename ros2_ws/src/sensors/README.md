# Sensors

Hardware acquisition only. Nodes publish measurements; calibration, filtering,
heading selection, CSV logging and shutdown policy belong to data_elaboration.

## Configuration and endpoints

- config/params.yaml: all deployment parameters for nodes in this package.
  Missing parameters fail explicitly; there are no hidden hardware defaults.
- config/endpoints.yaml: the only source for sensor topic names.
- sensors/generated/ros_endpoints.py: generator output imported by publishers
  and by downstream packages. build.sh regenerates it before colcon.
- Register addresses, protocol frames and SI unit conversions remain in drivers:
  they define the protocol rather than the installation configuration.
- The front/back ultrasonic instances select their generated endpoint group from YAML.
  Front is enabled. Back is optional and defaults to enabled: false: its node
  stays idle without opening the serial port, creating a publisher or a timer.
  Set ultrasonic_back_node.ros__parameters.enabled to true when installed.
  ttyUSB0 (front) and ttyUSB1 (back) are provisional assignments, not verified wiring.

## Acquisition

| Node | Interface | Message / topic |
| --- | --- | --- |
| ultrasonic_front_node | ttyUSB0 | sensor_msgs/Range /ultrasonic/front (m) |
| ultrasonic_back_node | ttyUSB1 | sensor_msgs/Range /ultrasonic/back (m) |
| gps_node | ttyUSB2, NAV-PVT | sail_msgs/GpsData /gps/data |
| i2c_sensors_node | bus 1, mux 0x70, channel 2 | sensor_msgs/Imu /imu/data |
| i2c_sensors_node | same mux, channel 0 | geometry_msgs/Vector3Stamped /compass/data |
| battery_node | gpiochip0 line 13 | std_msgs/Bool /battery/data |

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

live_sensors.launch.py and replay_sensors.launch.py are intentionally identical:
both start all acquisition nodes, including IMU via i2c_sensors_node.
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
