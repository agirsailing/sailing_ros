# communication_web

Two gateways inspired by Polimi's `web_communication`: one for telemetry, one
for commands. The existing Agir package name remains `communication_web`.

`telemetry_gateway_node` aggregates processed data, publishes two custom ROS
messages from `sail_msgs`, and forwards the same structures as MQTT JSON.
`command_gateway_node` exposes only the existing rosbag start/stop services.
There are no mark, actuator, update or shutdown commands in this gateway.

## Telemetry contract

| ROS output | Message | MQTT output |
| --- | --- | --- |
| `/web/telemetry` | `sail_msgs/WebTelemetry` | `agir_gui/data/telemetry` |
| `/web/position` | `sail_msgs/BoatPosition` | `agir_gui/data/position` |

Both snapshots default to 10 Hz and contain `header.stamp.sec` and
`header.stamp.nanosec` in ROS time. In live mode this is system time; when all
participating nodes use simulated time it follows `/clock`. Their `frame_id` is
empty because these aggregates mix quantities expressed in different frames.

`WebTelemetry` contains:

- `roll_deg`, `pitch_deg`, `yaw_deg` and `attitude_valid`, sourced from
  `/processed/imu/rpy/aero`. Positive roll means right side down; positive pitch
  means bow up; positive yaw means turning right. Yaw is relative to IMU startup,
  **not geographic heading**. The gateway performs no additional conversion.
- `height_m` and `height_valid`, from `/processed/boat_height`: signed vertical
  clearance of the design-waterline reference below the centre of mass.
- `battery_low` and `battery_valid`, from `/processed/battery/low`.
  `battery_valid=false` means unknown; a false low-alarm bit is not a charge
  percentage, voltage measurement or confirmation of overall battery health.
- `sog_mps` and `sog_valid`, from `/processed/gps/summary`.

`BoatPosition` contains `latitude_deg`, `longitude_deg`, `sog_mps`, `fix_valid`
and the original `gps_stamp`. Invalid, non-finite, out-of-range or expired GPS
fixes invalidate all three values. GPS freshness uses `gps_stamp`, not the
summary's periodically refreshed header. Attitude and height freshness use their
source headers. The un-stamped battery Bool uses reception time.

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
  "sog_valid": true,
  "sog_mps": 6.0
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
