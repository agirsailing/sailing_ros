# Agir Sailing Team ROS 2

ROS 2 Jazzy workspace for the KTH Agir Sailing Team.

- [Docker setup for PC and Raspberry Pi](Docker/README.md)
- Sensor package: `ros2_ws/src/sensors`
- Web communication package scaffold: `ros2_ws/src/communication_web`
- Data processing package scaffold: `ros2_ws/src/data_elaboration`
- Sensor configuration: `ros2_ws/src/sensors/config/params.yaml`

Inside the configured container:

```bash
bash /home/ros/ros2_ws/scripts/build.sh
bash /home/ros/ros2_ws/scripts/run.sh live
```

The launch requires the actual ultrasonic, GPS, I2C and GPIO hardware.
The IMU node is available separately and is not launched by default.

Node files, executables and ROS node names use the `_node` suffix. Helper modules
do not use that suffix. The two new package scaffolds contain no application nodes yet.
