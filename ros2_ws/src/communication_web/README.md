# communication_web

Two gateways inspired by Polimi's `web_communication`: one for telemetry, one
for commands. The existing Agir package name remains `communication_web`.

`telemetry_gateway_node` aggregates processed attitude/height and raw GPS, battery and range snapshots, publishes two custom ROS
messages from `sail_msgs`, and forwards the same structures as MQTT JSON.
`command_gateway_node` exposes only the existing rosbag start/stop services.
There are no mark, actuator, update or shutdown commands in this gateway.

## Telemetry contract

| ROS output | Message | MQTT output |
| --- | --- | --- |
| `/web/ros/dashboard` | `sail_msgs/DashboardDataMsg` | `agir_gui/data/dashboard` |
| `/web/ros/map` | `sail_msgs/MapDataMsg` | `agir_gui/data/map` |

ROS and MQTT receive the same snapshot independently. The ROS outputs allow
local inspection and recording: rosbag_manager uses `ros2 bag record -a`, which
records ROS topics, not MQTT traffic. MQTT delivers JSON to the browser.

The MQTT names replace `agir_gui/data/telemetry` and `agir_gui/data/position`;
deploy the gateway and web app together and update any broker topic ACLs.
The ROS outputs are `/web/ros/dashboard` and `/web/ros/map`, with types
DashboardDataMsg and MapDataMsg respectively. Rebuild consumers; old bags retain their original message types.
MapDataMsg now uses the existing Agir position fields below, replacing the unused
legacy definition with wind/marks fields. JSON payload fields are unchanged.

Dashboard and map have independent timers, configured at startup in `config/params.yaml`:

```yaml
dashboard_publish_rate_hz: 3.0
map_publish_rate_hz: 3.0
```

Each timer publishes only its own ROS message and matching MQTT message. Both
rates must be finite and strictly positive; zero/on-data is not supported here.
Replace the former single `publish_rate_hz` in custom gateway YAML files with
these two keys and restart/relaunch after installing the updated configuration.
Changing a rate does not change source-node frequencies or freshness timeouts.
Recording state has a third, MQTT-only timer:

```yaml
recording_state_publish_rate_hz: 0.5
recording_state_timeout_s: 1.5
```

The manager still publishes ROS state at 2 Hz plus immediate start/stop/failure
updates. The gateway caches the latest state and sends it over MQTT every 2 s,
including changes on the next tick (no extra immediate MQTT state publication).
Command responses remain independent and are returned when ready.
`RecordingState` has no source header, so the shared freshness helper checks
monotonic elapsed time since receipt. If no state arrives for more than 1.5 s,
the next MQTT state tick drops the cache and sends nothing. It never repeatedly
asserts an old state after the manager disappears. All parameters above must be
positive and finite and must be included in custom gateway YAML files. Browser
staleness detection must allow more than the 2 s MQTT interval plus network jitter.

Both snapshots contain `header.stamp.sec` and
`header.stamp.nanosec` in ROS time. In live mode this is system time; when all
participating nodes use simulated time it follows `/clock`. Their `frame_id` is
empty because these aggregates mix quantities expressed in different frames.

`DashboardDataMsg` contains:

- `roll_deg`, `pitch_deg`, `yaw_deg` and `attitude_valid`, computed by the gateway
  from `/processed/imu/data/aero` (`sensor_msgs/Imu.orientation`). The quaternion
  is normalized and checked; absent/invalid orientation makes the angles invalid.
  Mounting and world/body conventions have already been applied by processing.
  Roll is in [-180, 180] degrees (right side down positive); pitch in [-90, 90]
  (bow up positive). Yaw is in **[0, 360)**, clockwise from magnetic north with
  BNO085 `rotation_vector`: 359 -> 0 -> 1 is the normal crossing of north.
  It is not GPS course or declination-corrected true heading. No turn count is kept.
  At pitch +/-90, Euler roll and yaw cannot be separated; the converter uses roll=0
  and an equivalent yaw. The underlying quaternion stays available without this
  Euler singularity. Game rotation vector / raw fallback does not establish north.
- `height_m` and `height_valid`, from `/processed/boat_height`
  (`marti_common_msgs/Float64Stamped.value`): signed vertical clearance in metres
  of the design-waterline reference below the centre of mass. Source publication
  is configured at 20 Hz; cached repeats retain the original measurement stamp.
  Rebuild the image for `marti_common_msgs` and clean-build the workspace after
  migrating from the removed `BoatHeight` interface. Web payload fields are unchanged.
- `battery_low`, `battery_voltage_v` and `battery_valid`, directly from
  `/battery/data` (`sail_msgs/BatteryData`). The gateway displays the raw GPIO
  alarm; battery_node itself confirms alarms and requests shutdown.
  `battery_valid` indicates a fresh snapshot and known alarm, not voltage validity
  or overall health. Voltage can independently be NaN (JSON null), even while
  the low alarm remains valid. No charge percentage is calculated.
- `sog_mps` and `sog_valid`, directly from `/gps/data` (`gps_msgs/GPSFix.speed`).
- `ultrasonic_left_m` / `ultrasonic_left_valid` and
  `ultrasonic_right_m` / `ultrasonic_right_valid`, from `sensor_msgs/Range`
  on `/ultrasonic/left` and `/ultrasonic/right`. These are raw beam distances
  in metres, not the attitude-corrected height. Each side must be finite, within
  its sensor's min/max range and fresh by both source and reception time.
  `ultrasonic_timeout_s` defaults to 0.5 seconds; one missing sensor does not
  invalidate the other sensor or the rest of the telemetry.

`MapDataMsg` contains `latitude_deg`, `longitude_deg`, `sog_mps`, `fix_valid`
and the original `gps_stamp`. Invalid, non-finite, out-of-range or expired GPS
fixes invalidate all three values. GPS status must be at least `GPSStatus.STATUS_FIX`.
GPS freshness uses the original `GPSFix.header.stamp`, copied to map `gps_stamp`.
All inputs use the shared freshness helper on source headers and reception time.
A fresh no-fix message invalidates position/SOG at the next snapshot. A missing
or stale IMU does not invalidate GPS, and vice versa. GPS `track` (course) remains
available on `/gps/data`; the web message schemas have not been extended.

There is no intermediate navigation selector or GPS summary. After updating,
clean-build the workspace to remove the old installed node/message. Custom launches
and subscribers to the removed `/processed/gps/summary` or `/processed/heading_deg`
need updating. Keep GPS/attitude timeout settings in this package's YAML.

Each input expires independently using the timeouts in `config/params.yaml`.
Missing/stale numbers are NaN in ROS and **null in JSON**, with false validity
flags. Snapshots continue even if a sensor has never published. Snapshots are
latest-value aggregates, not measurements synchronized to a single acquisition.

Example MQTT telemetry payload:

```json
{
  "header": {"stamp": {"sec": 1789552800, "nanosec": 0}, "frame_id": ""},
  "attitude_valid": true,
  "roll_deg": 12.0,
  "pitch_deg": 1.5,
  "yaw_deg": 32.0,
  "height_valid": true,
  "height_m": 0.45,
  "battery_valid": true,
  "battery_low": false,
  "battery_voltage_v": 12.4,
  "sog_valid": true,
  "sog_mps": 6.0,
  "ultrasonic_left_valid": true,
  "ultrasonic_left_m": 0.62,
  "ultrasonic_right_valid": true,
  "ultrasonic_right_m": 0.58
}
```

Example MQTT position payload:

```json
{
  "header": {"stamp": {"sec": 1789552800, "nanosec": 0}, "frame_id": ""},
  "gps_stamp": {"sec": 1789552799, "nanosec": 900000000},
  "fix_valid": true,
  "latitude_deg": 59.3293,
  "longitude_deg": 18.0686,
  "sog_mps": 6.0
}
```

## Rebuild after interface changes

BatteryData replaces Bool on `/battery/data`; `/battery/voltage` is removed.
Rebuild and restart sensors and the gateway together.
Old bags containing Bool on `/battery/data` are not directly compatible with
this new subscriber type. Update the dashboard alongside the gateway to show volts.

After updating BatteryData or DashboardDataMsg, rebuild the interfaces and all
consumers before restarting the nodes. Inside the ROS container, from `ros2_ws`:

```bash
bash scripts/build.sh --clean
source install/setup.bash
```

This also regenerates endpoint constants and builds sensors, data_elaboration
and communication_web. Restart their publishers/subscribers against the rebuilt
interfaces. The web app's voltage display remains unknown with an older gateway.

## Recording commands


| MQTT request | ROS service | MQTT response |
| --- | --- | --- |
| `agir_gui/cmd/start_recording` | `/local_cmd/start_recording` (`StartRecording`) | `agir_gui/rsp/start_recording` |
| `agir_gui/cmd/stop_recording` | `/local_cmd/stop_recording` (`StopRecording`) | `agir_gui/rsp/stop_recording` |

Send a JSON object such as `{"requestId":"recording-001"}` with **retain=false**
and preferably MQTT QoS 1. Each new action needs a unique requestId. The services
have empty requests: directory, name and MCAP settings belong to rosbag_manager.
The response follows the Polimi schema:

```json
{"requestId":"recording-001","success":true,"error_message":"","bag_name":"rosbag2_..."}
```

The bag name comes from `effective_bag_name` for start and `last_bag_name` for
stop. `/local_state/recording_state` is also forwarded by the telemetry node to
`agir_gui/data/recording_state`, with `recording`, `bag_name`, `last_error`.
It is a periodic, non-retained state stream; the UI should mark it unknown when
messages stop arriving, rather than keep showing an old recording state.

Calls are asynchronous, one at a time. Retained commands and unknown command
topics are ignored. A bounded requestId cache prevents repeats while pending and
replays completed responses without calling ROS again. This cache is in memory,
bounded and lost at restart; it does not promise exactly-once execution across
restarts. A busy response means retry later; an unavailable-service response
requires a new requestId after the manager is ready. Malformed JSON is rejected.
Oversized commands and a full input queue are logged and dropped.

The configurable service timeout uses wall time. On timeout the actual operation
may still complete: check the recording-state stream before deciding what to do.
If a reply is lost during a broker outage, the web app can retry the same requestId
to retrieve its cached response. Sending a command alone never proves success.

## Configuration and launch

All ROS/MQTT names are in `config/endpoints.yaml` and its matching generated Python
constants. Configuration is split into:

- `config/params.yaml`: normal node settings, tracked in Git.
- `config/mqtt_config.example.yaml`: public template with placeholders.
- `config/mqtt_config.yaml`: local broker settings and credentials, ignored by Git.

Copy the example to `mqtt_config.yaml` on each machine, then configure **both**
gateway sections before building. A placeholder copy is provided in this working
tree; it contains no real credentials. The native MQTT/TLS hostname and port are
for the Raspberry, not the browser's WebSocket URL. The example enables verified
TLS on port 8883; confirm the port with your provider. An empty CA path uses
system trust. Replace the `.invalid` hostname and placeholder username/password.

Both launchers load the normal parameters followed by the MQTT file. They accept
`communication_web_params_file` and `communication_web_mqtt_config_file` for
absolute-path overrides. A missing MQTT file produces an explicit setup error;
the example is not used as a silent fallback. Local YAML files are copied into
the ROS install by the existing `setup.py`; rebuild after edits, or use the
absolute-path override.
**The local source and install copies contain credentials**: keep them on the
development machine/Pi, restrict access, and do not publish build artifacts.
Gitignore protects new files from accidental commits; it cannot remove secrets
already committed in history. Do not put this file in the web app.

No broker or web server is started here. Paho MQTT >= 2 is installed by the Agir
Dockerfiles. Each gateway adds a unique suffix to its MQTT client ID.

The sibling `sailing_web` dashboard uses the same MQTT contract. Browser operators
enter their own broker client credentials at connection time. Give boat and
operator credentials separate permissions; neither needs broker-admin access.

MQTT connection/reconnection is asynchronous. ROS snapshots remain available
without a broker. Data is non-retained, defaults to QoS 0 and is not buffered
offline; commands/replies default to QoS 1. No backfill/history is provided.

- `live_communication.launch.py`: telemetry plus recording commands.
- `replay_communication.launch.py`: telemetry only; no recording command gateway.
- `communication_web_launch.py`: compatibility include for the live launcher.

Orchestrator already includes the respective communication launchers. Its replay
sensor pipeline still starts hardware nodes: bag-only replay is a separate TODO.
When that is implemented, enable `use_sim_time` consistently with the processing
nodes and provide bag `/clock`; avoid replaying recorded `/web/*` snapshots while
regenerating them. The replay processing launch does not run the battery monitor,
so the battery remains unknown unless its processed topic is supplied by a bag.

## Offline checks

The standard-library tests in `test/` use fake messages and services, without ROS,
MQTT connections or hardware. They cover validity/timeouts, strict JSON,
recording responses, duplicate requests and configuration/wiring. They do not
replace a ROS build or a broker integration test.

### Command processing rate and interface migration

`command_gateway_node.process_rate_hz: 20.0` checks queued commands, service
responses and timeouts every 50 ms using a steady clock. It does not publish
commands or responses periodically. Replace `poll_period_s` in custom YAML with
`process_rate_hz` (Hz = 1 / old seconds); positive finite values are required.

`RollPitchYaw` and both `/processed/imu/rpy*` topics have been removed. Clean-build
the workspace and restart producers/consumers. The gateway now takes standard Imu;
web field names are unchanged, but yaw is wrapped instead of accumulating turns.
External ROS subscribers and RPY-only bags must migrate to the Imu topics.
