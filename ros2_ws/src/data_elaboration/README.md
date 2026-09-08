# data_elaboration

Sensor data processing for the Agir Sailing Team.

This is an empty `ament_python` package. No application nodes are implemented yet.

- Put node implementations in `data_elaboration/<name>_node.py` and use
  `<name>_node` for both the executable and the ROS node name.
- Keep helper modules separate, without the `_node` suffix.
- Register node executables in `setup.py`.
- Add nodes to `launch/data_elaboration_launch.py`.
- Store their parameters in `config/params.yaml` and load that file from the launch.
  The YAML keys must match the ROS node names.

The launch file currently starts no nodes. No web protocol, topics or processing
algorithms have been selected.
