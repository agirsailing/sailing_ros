# Workspace scripts

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../../README_ENG.md)

Run inside the ROS container from `/home/ros/ros2_ws`. These scripts do not
install Docker, update Git or configure host hardware.

| Script | Usage | Behaviour |
|---|---|---|
| [build.sh](build.sh) | `bash scripts/build.sh --clean` | Clean by default: removes build/install/log, generates endpoints, builds interfaces and workspace |
| [build.sh](build.sh) | `bash scripts/build.sh --incremental` | Reuses build/install for ordinary source changes |
| [run.sh](run.sh) | `bash scripts/run.sh live` | Sources environments and starts orchestrator; requires an existing build |
| [run.sh](run.sh) | `bash scripts/run.sh replay` | Starts processing and telemetry with simulated time; ros2 bag play supplies sources |
| [test.sh](test.sh) | `bash scripts/test.sh` | Incremental build and all tests |
| [test.sh](test.sh) | `bash scripts/test.sh --no-build sensors sail_common` | Only selected package tests, without building |
| [test.sh](test.sh) | `bash scripts/test.sh --clean-build --summary` | Clean build and compact summary |

`PARALLEL_WORKERS` defaults to 2. Example:

```bash
PARALLEL_WORKERS=2 bash scripts/build.sh --incremental
bash scripts/test.sh --no-build data_elaboration communication_web
```

With package arguments, test.sh's incremental build includes the selected packages
and their dependencies; `--clean-build` instead rebuilds the entire workspace.
Both modes test only the selected packages.
With `--no-build`, ensure sources match the build. Inspect
XML results: a skip does not prove behaviour. Parser/freshness/geometry tests
do not certify real sensors, networking or calibration. See the following sections for system checks.

To add tests, follow existing package tests: pytest for Python, ament/GTest where
configured. Declare test dependencies in package.xml and register tests with the
build system. Isolate drivers/brokers with fakes in unit tests; test ROS integration
and hardware separately. Cover expired/missing data, backwards clock jumps,
malformed input and geometric boundaries.

Arguments following `live`/`replay` are forwarded to ros2 launch. `bag_full_topic`
is an unconfigured placeholder. Do not confuse this run.sh with the host script
in DAY_BEFORE_REGATTA or the MQTT diagnostics launcher.

## 1. PC checks inside the ROS container

```bash
cd /home/ros/ros2_ws
bash scripts/test.sh --clean-build
bash scripts/test.sh --no-build communication_web sail_common
colcon test-result --verbose
```

The first test invocation clean-builds and tests all packages; the second is a
targeted alternative after a valid build. You need not run both for every edit.
Lint errors differ from functional failures: read summaries/XML, not just the
last terminal line. A skip is not a pass and needs explanation. `--no-build`
does not generate missing interfaces.

Tests cover decoders, geometry, freshness/caches, rosbag lifecycle and gateways.
`test_*pipeline_ros.py` uses real ROS/DDS in the container with mocked hardware
or MQTT; it does not validate EMQX or wiring. Deployment shell tests use temporary
copies and simulated administrative commands.

## 2. Web app only — PC terminal in the web repository

```powershell
node --test test/*.test.js
```

For MQTT contract changes check both repositories: names, fields, units, null/NaN,
rates, timeouts, roles and reconnection behavior.

## 3. Raspberry and boat

Follow [manual checks](../../guides/inglese/ros_system_startup.md) and record commit, installed YAML,
wiring, network and outcomes. Measure rates with `ros2 topic hz`, but also check
unique timestamps: 50 messages/s does not establish 50 new measurements/s.
Test source loss/recovery without manufacturing fresh data.

## PR criteria

- Document behavior and parameters in the package README.
- Pass relevant tests and state hardware limitations.
- Register new interfaces in CMake and dependencies in package.xml/Dockerfiles.
- Regenerate endpoints and update consumers, including the web app when required.
- Exclude private configs/tokens, `.venv`, build/install/log and recordings.
- For a bug, record before/after behavior and a reproducer, not just tests that
  mirror implementation details.
