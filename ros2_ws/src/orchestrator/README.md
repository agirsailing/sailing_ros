# Orchestrator

This ROS 2 package contains the top-level launch files for live and replay modes.
Live includes the live launches from sensors, data_elaboration, communication_web
and rosbag_manager. Replay includes the respective replay launches from sensors,
data_elaboration and communication_web; it never includes rosbag_manager.
sail_msgs contains interfaces only and has no launch. The orchestrator does not
include itself. communication_web currently returns an empty LaunchDescription,
ready for future nodes. Starting rosbag_manager does not itself start recording.
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
