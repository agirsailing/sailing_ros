# Tools outside the ROS runtime

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../README_ENG.md)

[mqtt_diagnostics](mqtt_diagnostics/README_ENG.md) simulates dashboard, map and
recording state and compares MQTT TCP/WebSocket reception. It runs on a PC or
Raspberry without a ROS container. A local Mosquitto broker uses Docker.

The endpoint generator and rosbag-to-CSV exporter live in
[workspace tools](../ros2_ws/tools/README_ENG.md). Never copy a Windows `.venv`
to the Raspberry or commit private configuration and large result folders.
