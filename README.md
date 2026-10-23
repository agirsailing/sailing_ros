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

The communication package publishes `/web/ros/dashboard` and `/web/ros/map` and
forwards them to MQTT under `agir_gui/data/`. Set the broker for both gateways in
`communication_web/config/mqtt_config.yaml` before using the web link. Live includes
recording commands; replay includes only the telemetry gateway.

## Live architecture

One left-to-right overview of the live system. Blue ovals are ROS nodes; orange
rectangles are topics. Solid `pub` arrows go from publishers to topics. Dashed
`sub` arrows also point from nodes to topics and express subscription, not message
travel direction. Each topic is shown once, even when it has multiple subscribers.
Hardware access, service calls and process control have their own labels.

[![Live architecture: hardware to browser, left to right](docs/architecture/live-architecture.svg)](docs/architecture/live-architecture.svg)

Click the diagram to open the full-size vector image. Its column positions are
fixed so README renderers cannot rearrange the architecture vertically.
Edit the [Graphviz source](docs/architecture/live-architecture.dot) and regenerate
with `neato -Tsvg docs/architecture/live-architecture.dot -o docs/architecture/live-architecture.svg`.
A [PNG copy](docs/architecture/live-architecture.png) is available for sharing.

For example, `ultrasonic_left_node` publishes once on `/ultrasonic/left`; the
height filter and telemetry gateway both subscribe to that same topic. The IMU
conversion chain is not a feedback loop: the aero callback publishes only aero
outputs. Height uses robotic orientation; the dashboard uses aerospace angles.
`/tf_static` contains static transforms, not periodic measurements.

The recorder subscribes to discovered ROS topics (summarized in one box to avoid
an edge to every topic), including ROS dashboard/map copies; it does not capture
MQTT directly. Service edges describe caller/server roles. The battery node also
checks its shutdown policy; reaching the host depends on the Docker deployment.

Diagnostic topics, parameter events and unused transformer magnetometer ports
are omitted. Names come from package `config/endpoints.yaml` and launch remappings.
This is the live architecture, not the standalone MQTT simulator. Replay still
requires hardware. Inspect the running graph with `ros2 node list`,
`ros2 node info /NODE_NAME` and `ros2 topic info /TOPIC_NAME --verbose`.

## Where frequencies are configured today

These are source defaults in this checkout. The deployed/installed YAML and
runtime parameters may differ. A timer frequency is a requested callback rate,
not a guarantee of fresh sensor samples or an exact output frequency.
This table uses branch `14-remove-central-publish_rate` at `79beeef` as its
baseline, with the ultrasound and GPS acquisition/publication splits described below.
For comparison, local `main` at `1458a25` has dashboard/map at **3 Hz** and
recording state every **2 s** (6.5 MQTT publications/s baseline). Reconcile these
values when merging branches; do not infer deployed settings from another branch.

| Node | Input reception / hardware acquisition | Computation | Publication | Configuration |
|---|---|---|---|---|
| `ultrasonic_left_node` | Reader thread waits for incoming serial data (`read_rate_hz: 0.0`); device frame rate is external | Parse complete frames as available; retain the latest valid sample and its decoding timestamp | Target 20 Hz on `/ultrasonic/left`, repeating the latest sample only while fresh (0.5 s maximum) | [sensors params](ros2_ws/src/sensors/config/params.yaml), `read_rate_hz`, `publish_rate_hz`, `max_sample_age_s` |
| `ultrasonic_right_node` | Independent reader, same arrival-driven mode as left | Same as left | Target 20 Hz on `/ultrasonic/right`, with the same freshness policy | sensors params, same three parameters |
| `gps_node` | Reader thread waits for incoming packets (`read_rate_hz: 0.0`); receiver output rate is external | Decode NAV-PVT and cache the latest solution, including `fix_valid=false`; other packets do not refresh its age | Target 10 Hz on `/gps/data`, preserving source stamps on repeats; stop after 1 s without new NAV-PVT | sensors params, `read_rate_hz`, `publish_rate_hz`, `max_sample_age_s` |
| `i2c_sensors_node`: IMU | Current LSM6DS3TR-C driver: device ODR 104 Hz, worker reads requested at 50 Hz; replacement BNO085 driver migration pending | Unit conversion and snapshot caching per successful read | Independent target 50 Hz on `/imu/data`; retain source stamp on repeats, expire after 0.5 s | sensors params, `imu.odr_hz`, `imu.read_rate_hz`, `imu.publish_rate_hz`, `imu.max_sample_age_s` |
| `i2c_sensors_node`: compass | Worker reads requested at 10 Hz on the shared mux | Conversion per read (unchanged 20 ms wait), snapshot caching | Independent target 10 Hz on `/compass/data`; retain source stamp on repeats, expire after 0.5 s | sensors params, `compass.read_rate_hz`, `compass.publish_rate_hz`, `compass.max_sample_age_s` |
| `battery_node` | Voltage decoded asynchronously from GPIO edges; sender sample rate is external. Low GPIO polled at 10 Hz | Cache voltage/alarm and evaluate shutdown on each successful read, independently of publication | Independent target 10 Hz on `/battery/data`; preserve GPIO stamp on repeats, stop after 0.5 s without a fresh alarm read; expired voltage becomes NaN after 5 s | sensors params, `read_rate_hz`, `publish_rate_hz`, `max_sample_age_s`, `voltage_max_age_s` |
| `imu_mount_transformer_node` | `/imu/data`, nominally up to 50 Hz | Transform each available input using TF | Input-driven `/internal/imu/mounted`, normally near input rate when TF is available | [processing params](ros2_ws/src/data_elaboration/config/params.yaml); no output timer |
| `imu_node` | Mounted IMU up to about 50 Hz AND aero-body input up to about 50 Hz | One filter update per mounted sample; separate conversion per valid aero-body sample | Up to about 50 Hz **per topic**: robotic IMU/RPY and aero IMU/RPY; static TF sent at initialization | processing params; no output timer |
| `imu_aero_transformer_node` | `/processed/imu/data`, up to about 50 Hz | Transform each available input using TF | Input-driven `/internal/imu/aero_body`, normally near input rate | processing params; no output timer |
| `ultrasonic_filter_node` | Left target 20 Hz + right target 20 Hz + robotic IMU up to about 50 Hz | Store attitude history on IMU callbacks; reject repeated range timestamps and attempt projection/fusion for new samples | Up to about **40 Hz**, often lower; only when frame, freshness, geometry and fusion checks pass | processing params; no output timer |
| `heading_node` | GPS up to 10 Hz + compass target 10 Hz; callbacks store latest inputs | Timer selects direction and builds summary at 10 Hz | 10 Hz **per topic**: `/processed/heading_deg`, `/processed/gps/summary`; snapshots may reuse inputs | processing params, `rate_hz` |
| `telemetry_gateway_node` | Independently receives aero RPY ~50, height up to ~40, battery ~10, GPS summary ~10, left/right up to 20 each, state 2 Hz plus events | Cache on input callbacks; build dashboard AND map at 4 Hz. State forwarded in its callback | Each ROS dashboard/map topic at 4 Hz; each corresponding MQTT topic at 4 Hz; MQTT state follows manager | [communication params](ros2_ws/src/communication_web/config/params.yaml), `publish_rate_hz` |
| `command_gateway_node` | MQTT commands on demand; asynchronous service responses | Queue/timeouts checked every 0.05 s (20 Hz) | MQTT responses on demand, **not** 20 messages/s | communication params, `poll_period_s` |
| `rosbag_manager_node` | Start/stop service requests on demand | Handle requests; check recorder process and build state every 0.5 s | State at 2 Hz, plus after start/stop handling | Interval hard-coded in [rosbag_manager_node.py](ros2_ws/src/rosbag_manager/rosbag_manager/rosbag_manager_node.py) |

The same node can have multiple input/output rates: summing the two IMU callbacks
into a single "node Hz" would hide what is actually happening. These are nominal
rates from code, not measurements on the Pi. Invalid inputs, missing TF, startup,
serial timeouts, I2C conversion waits and executor load can reduce actual throughput.
In particular, IMU and compass share a bus/mux lock despite separate acquisition
workers and publication timers: their requested read rates are not guarantees.
The battery's 100-baud link is a bit rate, not 100
voltage measurements/s. The two ultrasound callbacks can each publish a fused
height, so fusion does not imply one output per simultaneous left/right pair.

The live gateway therefore has a nominal baseline of **4 + 4 + 2 = 10 MQTT
publications/s**, plus recording-state updates caused by commands. This is
different from the diagnostic simulator's 5 Hz dashboard + 2 Hz map + 0.5 Hz
recording state (7.5 publications/s). A successful simulator run does not prove
that the real gateway, hardware or exact live load behaves identically.

Current nodes read their rate parameters and create timers at startup. Changing
a YAML file requires restarting/relaunching with that file (and rebuilding or
installing updated configuration when needed). There is no implemented generic
live rate/mode switching mechanism. To measure an output, run, for example,
`ros2 topic hz /ultrasonic/left` or `ros2 topic hz /web/ros/dashboard` inside the
configured ROS environment; this measures reception, not the sensor's hardware ODR.

## Acquisition design and proposed publication controls

Agir should keep one owner per independent hardware interface: one node for each
serial sensor and one owner for the shared I2C bus/multiplexer. Processing nodes
consume typed ROS messages without opening those devices. This keeps hardware
failures and device-specific timing separate and lets recordings feed processing.

In the Polimi implementation inspected for comparison, `central_node` owns one
serial connection, drains its packets with `readAll()` and publishes packet IDs
and payloads on `/serial/raw_rx`. Sensor-specific nodes decode that shared
transport; GPS has its own launch. Its `loop_freq_hz: 150` is a serial polling
frequency, not a guarantee that every sensor produces 150 new samples/s. That
design fits a shared multiplexed transport. Agir's independent serial devices
do not need to be combined into a single raw topic just to centralize settings.

Keep timing settings in each package's YAML as the single source of configuration;
there is no second general rates file. Ultrasound and GPS separate `read_rate_hz`
(zero means wait for incoming data) from `publish_rate_hz` (20 Hz for ultrasound,
10 Hz for GPS by default).
See the [sensor documentation](ros2_ws/src/sensors/README.md#ultrasound-reading-and-publication)
for timestamp preservation, stale-sample expiry and custom YAML migration.

**The following publication modes are future proposals for the other nodes,
not currently implemented parameters.**

```yaml
# Proposed example only: these publication.* parameters are not implemented yet.
heading_node:
  ros__parameters:
    publication.mode: periodic
    publication.rate_hz: 10.0

telemetry_gateway_node:
  ros__parameters:
    dashboard.publication.mode: periodic
    dashboard.publication.rate_hz: 5.0
    map.publication.mode: periodic
    map.publication.rate_hz: 2.0

rosbag_manager_node:
  ros__parameters:
    publication.mode: periodic
    publication.rate_hz: 0.5
```

- `on_data`: publish when a new valid sample/result is available, even if its
  numeric value equals the previous one. This is different from publishing only
  when a value changes. For a multi-input computation, specify which inputs
  trigger computation and how timestamp alignment/age limits are checked.
- `periodic`: publish the most recent usable result at the requested frequency.
  Do not accumulate a FIFO of old snapshots to replay later. Preserve acquisition
  timestamps and distinguish repeated samples, stale data and a missing source.
- Keep acquisition timing separate from output timing. Serial reception must
  continue draining data even when publishing slowly; I2C polling/data-ready and
  device ODR remain hardware concerns. GPS now continuously decodes packets by
  default and drains buffered packets when periodic reading is selected.
- Estimators should normally process every useful new sample, then optionally
  limit outgoing updates. Reducing an IMU filter's computation rate changes its
  behavior; it is not just a display-bandwidth choice. Similarly, do not reduce
  battery alarm/shutdown checking just to reduce outgoing telemetry frequency.
- Keep web dashboard and map snapshots independently rate-limited and retain a
  periodic recording-state heartbeat (for example every 2 s), even when immediate
  state-change updates are also provided. Broadcasting every sensor callback to
  MQTT would combine their rates into a potentially much higher message load.
- Implement startup selection first with validated modes/positive finite rates.
  Runtime parameter changes additionally need callbacks that safely replace timers
  and avoid duplicate publication; a successful `ros2 param set` alone is not proof
  that an existing timer changed.

Recommended order: expose the recording-state interval in YAML, separate dashboard
and map timers, then introduce the common publication policy while keeping hardware
readers and estimator input processing independent. Preserve existing defaults
until each behavior change has been tested against recorded data or hardware.
