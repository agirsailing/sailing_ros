# communication_web

Web communication for the Agir Sailing Team.

This is an empty `ament_python` package. No application nodes are implemented yet.

- Put node implementations in `communication_web/<name>_node.py` and use
  `<name>_node` for both the executable and the ROS node name.
- Keep helper modules separate, without the `_node` suffix.
- Register node executables in `setup.py`.
- Add nodes to `launch/communication_web_launch.py`.
- Store their parameters in `config/params.yaml` and load that file from the launch.
  The YAML keys must match the ROS node names.

The launch file currently starts no nodes. No web protocol, topics or processing
algorithms have been selected.
