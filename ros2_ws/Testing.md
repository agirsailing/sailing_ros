# Workspace tests

_Updated on: 30/10/2026_

Run tests inside the ROS container, from `/home/ros/ros2_ws`:

```bash
bash scripts/test.sh
```

This builds the workspace incrementally and runs its ROS package tests. See the
[workspace scripts guide](scripts/README_ENG.md) for package selection, clean builds,
result inspection and manual checks on the boat. The MQTT probe and bag exporter
have separate checks documented in their own READMEs.
