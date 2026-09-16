# Agir Sailing Team ROS 2

ROS 2 Jazzy workspace for the KTH Agir Sailing Team.

- [Docker setup for PC and Raspberry Pi](Docker/README.md)
- [Raspberry Pi 4 preparation and regatta updates](DAY_BEFORE_REGATTA/README.md)
- Sensor package: `ros2_ws/src/sensors`
- [Web communication: telemetry and rosbag commands](ros2_ws/src/communication_web/README.md)
- Data processing package: `ros2_ws/src/data_elaboration`
- Shared messages and services: `ros2_ws/src/sail_msgs`
- Live and replay launch package: `ros2_ws/src/orchestrator`

Inside the configured container:

```bash
bash /home/ros/ros2_ws/scripts/build.sh
bash /home/ros/ros2_ws/scripts/run.sh live
bash /home/ros/ros2_ws/scripts/run.sh replay
```

By default the build script cleans previous artifacts, loads ROS Jazzy, runs
`tools/gen_endpoints.py`, builds `sail_msgs`, then builds the complete workspace.
Set `PARALLEL_WORKERS` to override the default of two workers.
Use `bash scripts/build.sh --incremental` from `ros2_ws` to preserve build artifacts,
or `--clean` to explicitly rebuild from scratch. The quick Pi update uses incremental
mode unless the Docker image changes or you request a clean build.

The run script selects the corresponding launch in `orchestrator` and forwards
additional ROS launch arguments. Both modes now include sensor acquisition and
data processing. The live and replay sensor launches are intentionally identical
for now: both require the actual ultrasonic, GPS, I2C and GPIO hardware.
Replay does not start the battery shutdown policy and is not yet a bag-only mode.

Acquisition parameters live in `sensors/config/params.yaml`; processing parameters
live in `data_elaboration/config/params.yaml`. Each package's `endpoints.yaml`
defines its output topic names. Processing imports the generated sensor constants
for its inputs. See the package READMEs for the wiring and current limitations.

The communication package publishes `/web/telemetry` and `/web/position` and
forwards them to MQTT under `agir_gui/data/`. Set the broker for both gateways in
`communication_web/config/params.yaml` before using the web link. Live includes
recording commands; replay includes only the telemetry gateway.
