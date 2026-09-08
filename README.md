# Agir Sailing Team ROS 2

ROS 2 Jazzy workspace for the KTH Agir Sailing Team.

- [Docker setup for PC and Raspberry Pi](Docker/README.md)
- Sensor package: `ros2_ws/src/sensors`
- Web communication package: `ros2_ws/src/communication_web`
- Data processing package: `ros2_ws/src/data_elaboration`

Inside the configured container:

```bash
bash /home/ros/ros2_ws/scripts/build.sh
bash /home/ros/ros2_ws/scripts/run.sh live
```

The launch requires the actual ultrasonic, GPS, I2C and GPIO hardware.
The IMU node is available separately and is not launched by default.
