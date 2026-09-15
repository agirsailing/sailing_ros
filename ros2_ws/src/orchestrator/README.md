# Orchestrator

This ROS 2 package contains the top-level launch files for live and replay modes.
Both launch files include the matching launches from sensors and data_elaboration.
The two sensor launches intentionally start the same acquisition nodes, including
IMU and compass through i2c_sensors_node. Replay still requires hardware and does
not start rosbag playback. Its processing launch omits the battery shutdown policy.

After building and sourcing the workspace, use:

```bash
ros2 launch orchestrator live_system.launch.py
ros2 launch orchestrator replay_system.launch.py
```

The workspace wrapper provides the same modes through `bash scripts/run.sh live`
and `bash scripts/run.sh replay`. This package contains no node executables.
