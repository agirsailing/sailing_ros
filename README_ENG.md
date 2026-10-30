# Agir onboard system — ROS 2

_Updated on: 30/10/2026_

[Italiano](README.md)

This repository contains the ROS 2 onboard software developed by the **KTH Agir Sailing Team**.

**Maintainer:** Ettore Cirillo — [ettore.cirillo.dev@gmail.com](mailto:ettore.cirillo.dev@gmail.com).

## Introduction

The system acquires sensor data, processes attitude and estimates the height of the boat's design waterline above the water. It also manages MQTT telemetry to the webapp, buoy ping and ROS session recording in MCAP format. The webapp lives in the separate `agir_boat_monitoring` repository.

The software runs on the onboard Raspberry Pi 4 with ROS 2 Jazzy in Docker and is managed over SSH without a screen or desktop session. Docker also supports development and testing on a PC. This README provides an overview and points to guides and package documentation for details.

## Repository structure

| Directory | Path | Purpose | Detailed README |
|---|---|---|---|
| `DAY_BEFORE_REGATTA` | [`DAY_BEFORE_REGATTA/`](DAY_BEFORE_REGATTA/) | Raspberry configuration, updates, startup and autostart. | [English](DAY_BEFORE_REGATTA/README_ENG.md) |
| `Docker` | [`Docker/`](Docker/) | Container environments for PC and Raspberry Pi. | [English](Docker/README_ENG.md) |
| `guides` | [`guides/`](guides/) | Installation, operation, verification and maintenance procedures. | [English](guides/README_ENG.md) |
| `ros2_ws` | [`ros2_ws/`](ros2_ws/) | ROS 2 workspace with packages and build/test tools. | [English](ros2_ws/README_ENG.md) |
| `tools` | [`tools/`](tools/) | MQTT diagnostics independent of sensors and the ROS runtime. | [English](tools/README_ENG.md) |

Open each directory's detailed README to learn more about its contents.

## First steps

1. Start with the [guide index](guides/README_ENG.md): it covers prerequisites, PC setup and connecting to the Raspberry over SSH.
2. Read the [workspace overview](ros2_ws/README_ENG.md), including the package relationship diagram, then open the relevant package README for node and topic details.
3. To prepare the boat follow [Raspberry first installation](guides/inglese/raspberry_setup.md), then [manual startup and checks](guides/inglese/ros_system_startup.md). Enable autostart after these checks.
4. For build and test commands, see the [workspace scripts](ros2_ws/scripts/README_ENG.md).
