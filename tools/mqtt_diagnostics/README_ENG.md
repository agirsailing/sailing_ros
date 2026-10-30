# MQTT diagnostics without sensors

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../../README_ENG.md)

[probe.py](probe.py) creates a synthetic publisher and two observers, TCP and
WebSocket, with distinct client IDs. It isolates transport/broker from ROS.
It does not read sensors or implement recording/mark-ping services. An open
browser adds visual verification of the webapp.

## Raspberry over SSH: one command

Prerequisites: updated repository, real runtime stopped, configured private
`ros2_ws/src/communication_web/config/mqtt_config.yaml`. On the Pi host:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros/tools/mqtt_diagnostics
bash run.sh webapp --dashboard-hz 3 --map-hz 3 --state-hz 0.5
```

The wrapper prepares Python/venv and dependencies (may request sudo for Debian
apt), creates `config.local.json` from `config.ros.example.json` if missing, and
reuses broker, TCP port, TLS and credentials from ROS YAML. Docker is unnecessary
for this test. WebSocket settings come from JSON: default port **8084**, path
**/mqtt**; check them against your endpoint. Existing JSON is not overwritten,
so inspect any overrides.

Open one webapp without Demo, log in and watch ULTRASONIC LEFT/RIGHT throughout
the test. Values change with every dashboard message. Duration is 900 s. Note
UTC times of delays/disconnections, network/hotspot, number of tabs and connected
clients; change one variable at a time between comparisons.

**Rates:** the command above matches current nominal ROS→MQTT frequencies,
3+3+0.5 = 6.5 publishes/s. Plain `bash run.sh` instead uses dashboard 5 Hz, map
2 Hz, state 0.5 Hz (7.5/s). It does not reproduce ROS acquisition or guarantee
identical payload/load. The ramp changes by 2 cm per message; its period changes
when the rate increases.

## Windows cmd, without a ROS container

Install Python 3.10+ with the `py` launcher if missing. Open cmd:

```bat
cd /d C:\Users\ettor\Desktop\Agir_Sailing_Team\sailing_ros\tools\mqtt_diagnostics
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Only if `config.local.json` does not exist:

```bat
copy config.ros.example.json config.local.json
```

With configured ROS MQTT YAML and real publishers stopped:

```bat
.venv\Scripts\python.exe probe.py --config config.local.json --ros-config ..\..\ros2_ws\src\communication_web\config\mqtt_config.yaml --duration 900 --dashboard-hz 3 --map-hz 3 --state-hz 0.5 --ultrasonic-pattern ramp --webapp
```

For ROS-based JSON `publisher` can remain `{}`. Observers inherit publisher
credentials unless explicitly overridden. Without YAML use
[config.example.json](config.example.json), fill host/ports/TLS and provide
`MQTT_USER`/`MQTT_PASSWORD` via environment or prompts. Never commit secrets.

## Modes and isolation

| Bash command | Behaviour |
|---|---|
| `bash run.sh setup` | Prepare Python environment only |
| `bash run.sh webapp ...` | Prepare environment and publish to real `agir_gui/data/...` topics |
| `bash run.sh cloud --ros-config ../../ros2_ws/src/communication_web/config/mqtt_config.yaml` | Use config.local.json with isolated topics; run setup first |
| `bash run.sh local --duration 900` | Start Docker Mosquitto and use local.json; run setup first |
| `bash run.sh local-logs` | Local broker logs |
| `bash run.sh local-down` | Stop local broker |
| `bash run.sh analyze runs/RUN_NAME` | Regenerate analysis from saved files |

For isolated cloud testing first create local JSON as above. Without `--webapp`,
topics are `agir_diag/<run_id>/...`; the production browser does not see them.
Direct probe defaults are 2/2/0.5 Hz and a step every 5 s: specify ramp for changes
on every message. `--qos 0|1`, `--protocol 311|5`, `--decimals N` support controlled
comparisons; decimals does not round coordinates/timestamps. ACLs must allow test
topics. Never run simulator and real boat publishers on the same topics together.

Local Mosquitto exposes TCP `127.0.0.1:18883`, WS `127.0.0.1:19001`, without TLS.
An HTTPS webapp configured for cloud WSS does not automatically use that broker.
Local success does not certify EMQX, the hotspot or browser rendering.

## Results and interpretation

Each test creates `runs/<date-id>/`:

| File | Contents |
|---|---|
| `run.json` | Run metadata/settings, without credentials |
| `events.jsonl` | Connections, disconnections, publishes and errors with UTC times |
| `samples.csv` | Received samples, sequences, sizes and latencies |
| `summary.json` | Structured metrics per observer/stream |
| `report.md` | Readable report |

Compare actual duration, observed Hz, unique/duplicate sequences, maximum gap,
p50/p95/max and first/last-minute medians. Latency is from synthetic publish to
Python callback, on one monotonic clock: it **does not measure browser rendering**.
Client acceptance does not prove delivery, especially at QoS 0. Check missing
streams and disconnects too; no samples is not success.

If interrupted, preserve the whole run directory and use analyze. Copy the run
directory from Pi to PC, not `.venv`. Correlate EMQX using UTC/client ID/reason
codes; a generic transport error does not prove a plan limit.
[VALIDATION.md](VALIDATION.md) preserves a historical tool check, not certification
of the current boat configuration.
