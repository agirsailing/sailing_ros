# Workspace tools

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../../README_ENG.md)

## Endpoint generation

[gen_endpoints.py](gen_endpoints.py) reads `src/**/config/endpoints.yaml`, resolves
`@...` references and generates Python modules/C++ headers requested by
`meta.generate`. Build/test scripts invoke it. Manual execution in the container,
from the workspace root:

```bash
python3 tools/gen_endpoints.py
```

Edit source YAML files rather than patching generated output. After topic changes
update consumers, documentation, tests and MQTT contracts if affected. The
generator does not automatically create code subscribers/publishers.

## Export all rosbag topics to CSV

[allbags_to_csv.py](allbags_to_csv.py) exports **every topic present in each bag**,
without presets, filters or hardcoded topic names. It converts existing recordings;
it does not record new data and does not require replay or live nodes.

Inside the ROS container, from the built workspace root:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 tools/allbags_to_csv.py /path/to/recordings --output-dir /path/to/csv
```

Replace paths with locations accessible inside the container. The first argument
can be one bag containing `metadata.yaml`, or its parent directory (one level of
discovery). Directories named `rosbag2_*` are also recognized. Without `--output-dir`,
output goes into the current directory. Each bag gets its own subdirectory, named
after the bag with the optional `rosbag2_` prefix removed.

- One CSV per topic, including topics without samples; similar topic filenames
  receive distinct suffixes to avoid collisions.
- `timestamp_ns` is the bag recording timestamp in nanoseconds. A message timestamp
  remains in `header.stamp.sec` and `header.stamp.nanosec`. A custom field named
  `timestamp_ns` becomes `message.timestamp_ns` to preserve the bag timestamp.
- Nested fields become columns such as `orientation.x`; arrays and message sequences
  remain in JSON cells, including variable-length sequences.
- Uses installed ROS message types, including workspace custom types; no pandas
  dependency. Supports installed ROS storage plugins, including MCAP and SQLite3.
- Re-exporting overwrites CSVs with the same names: use a separate output directory
  for each analysis. Errors produce a nonzero exit code; partial files from a failed
  bag must not be treated as complete exports.

Temporary MCAP/SQLite3 bag tests: `python3 -m pytest tools/tests/test_allbags_to_csv.py`.

## Legacy utilities

[gen_bag_test.py](gen_bag_test.py) simulates old `/serial/raw_rx`, `/gps_data` and
`/gps_vel_data` topics and is not adapted to current Agir messages.
For recording and inspecting bags, see the [rosbag_manager README](../src/rosbag_manager/README_ENG.md).
ROS-independent MQTT diagnostics are in [tools/mqtt_diagnostics](../../tools/mqtt_diagnostics/README_ENG.md).
