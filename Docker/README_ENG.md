# Docker environment

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../README_ENG.md)

This directory contains the configuration for the project's ROS 2 Jazzy environments: one for PC development and one for running the system on the boat. Node source code stays in the [ros2_ws workspace](../ros2_ws/README_ENG.md); this directory defines the environment in which that code is built and run.

## Why we use Docker

The team develops on a PC and then transfers code to the Raspberry through Git. However, the program depends on more than the files we write: it also needs ROS, a compiler, message packages, and libraries for sensors and MQTT. Installing everything manually on each computer makes it harder to tell whether a problem comes from the code or a differently configured environment.

Docker lets us describe those installations in repository files. A new team member can build the environment from those instructions without installing ROS directly on Windows or macOS. On the Raspberry, application dependencies are also installed inside the container; the Raspberry operating system still manages networking, devices and startup services.

The PC and Raspberry have separate configurations because they serve different purposes. The PC needs development and analysis tools, including graphical windows when needed. The boat primarily needs sensor access and operation without a screen. We use the same ROS distribution and maintain the required dependencies in both environments, but build the code on each machine: PC build outputs must not be copied to the Raspberry.

## Images, containers and shared files

An **image** is the environment prepared by Docker: it contains ROS and the dependencies installed according to the `Dockerfile`. A **container** is a running environment created from that image. When VS Code attaches to the container, its terminal runs commands inside it, even though the VS Code window is on a Windows or macOS PC.

Project files are shared with the container through **mounts**, defined in `compose.yaml`. For example, editing a node in `ros2_ws/src` on the PC immediately makes the change visible in the corresponding container directory. You do not need to rebuild the Docker image for every code change; instead, rebuild the ROS workspace when required.

## Directory structure

```text
Docker/
├── pc_container/
│   ├── .dockerignore
│   ├── build.sh
│   ├── compose.gui.yaml
│   ├── compose.yaml
│   ├── Dockerfile
│   └── entrypoint.sh
├── raspi_container/
│   ├── .dockerignore
│   ├── compose.yaml
│   ├── Dockerfile
│   └── entrypoint.sh
├── README.md
└── README_ENG.md
```

These files have different roles and work together:

| File | Purpose |
|---|---|
| `Dockerfile` | Defines the base image, installs dependencies and prepares the container user and directories. |
| `compose.yaml` | Defines how to start the container: its name, image, shared files, network and, on the Raspberry, device access. |
| `entrypoint.sh` | Loads ROS and the workspace when the container starts, then executes the supplied command. |
| `build.sh` | On the PC, combines image building and container startup into one command. |
| `compose.gui.yaml` | Adds PC graphics configuration when running `build.sh --gui`. |
| `.dockerignore` | Excludes unnecessary files from the build context sent to Docker. |

## The two environments

| Feature | PC | Raspberry Pi |
|---|---|---|
| Directory | [pc_container](pc_container/) | [raspi_container](raspi_container/) |
| Purpose | Development, compilation, testing and recording analysis. | Reading sensors and running the onboard system. |
| Base image | `osrf/ros:jazzy-desktop-full` | `ros:jazzy-ros-core-noble` |
| Project image | `agirsailing:jazzy-desktop` | `agirsailing:jazzy-raspi` |
| Container name | `agir-ros-pc` | `agir-ros-raspi` |
| Directories shared from the host | `ros2_ws/src`, `scripts`, `tools`, `rosbags` | Entire `ros2_ws` |

Both containers use the `ros` account and workspace `/home/ros/ros2_ws`. This is a path inside the container: on the Raspberry host, the repository instead lives at `/home/boat/2025_SOFTWARE/sailing_ros`.

### PC — Development and testing

The [PC Dockerfile](pc_container/Dockerfile) starts from ROS Jazzy Desktop and adds the project libraries and development tools. It also includes visualization and analysis tools such as RViz and PlotJuggler, available when graphics are configured.

To build and start the environment, run from the `sailing_ros` root in **Git Bash on Windows** or **Terminal on macOS**:

```bash
bash Docker/pc_container/build.sh
```

The script uses [PC Compose](pc_container/compose.yaml). Normal startup requires neither a graphics server nor a shared GPU. Networking lets the container connect to the MQTT broker and lets ROS nodes communicate within it; direct ROS communication with other machines requires configuring that network connection as well.

To open RViz or other graphical tools, prepare a host X server first, then run `bash Docker/pc_container/build.sh --gui`. This adds [compose.gui.yaml](pc_container/compose.gui.yaml) and uses software rendering. The [PC setup guide](../guides/inglese/pc_setup.md) explains how to attach VS Code and build the code.

### Raspberry — Running on the boat

The [Raspberry Dockerfile](raspi_container/Dockerfile) starts from ROS Core and adds packages needed by the system: serial, I2C and GPIO access, GPS, processing, MQTT communication and rosbag recording.

[Raspberry Compose](raspi_container/compose.yaml) shares the whole workspace and the `/dev` device directory, exposing USB ports, the IMU UART and the I2C bus to the container. It uses host networking and IPC, with privileged execution for the hardware access configured by the project. Setup scripts prepare the host device names and permissions.

Use `DAY_BEFORE_REGATTA/complete_setup.sh` for initial installation and `DAY_BEFORE_REGATTA/quick_setup.sh` for updates. These scripts coordinate Docker and the ROS build. There is no need to run each Docker step manually: the [Raspberry setup guide](../guides/inglese/raspberry_setup.md) explains the full sequence.

The system can operate entirely over SSH, without Wayland, X11 or a desktop session. Manual startup uses [`DAY_BEFORE_REGATTA/run.sh`](../DAY_BEFORE_REGATTA/run.sh); autostart is enabled separately after testing.

## What happens when you start the container

The [PC entrypoint](pc_container/entrypoint.sh) and [Raspberry entrypoint](raspi_container/entrypoint.sh) load ROS Jazzy, enter the workspace and load `install/setup.bash` if the code has already been built. They then execute the supplied command, or open Bash.

A running container therefore means the environment is available, but does not mean all boat nodes are already running. There are three separate steps:

| Step | Result |
|---|---|
| Build the image and start the container | Prepares the environment with ROS and dependencies. On the PC, `Docker/pc_container/build.sh` does this. |
| Build the workspace | Prepares project packages and messages. Inside the container, run `bash scripts/build.sh` from `/home/ros/ros2_ws`. On the Raspberry, complete and quick already handle this. |
| Start the ROS system | Launches the nodes. On the Raspberry, `DAY_BEFORE_REGATTA/run.sh` runs this from the host. |

## What is saved and when to rebuild

On the PC, source files, scripts, tools and rosbags remain in the shared host directories. `build`, `install` and `log` instead stay inside the container: stopping and restarting it preserves them, whereas recreating it removes them and requires rebuilding the workspace. On the Raspberry, the entire workspace is shared, so these directories also remain on the host.

After source changes, use the [workspace scripts](../ros2_ws/scripts/README_ENG.md) to rebuild. When adding a system library, update the Dockerfile for the environment that needs it and rebuild the image; if both the PC and boat need it, update both Dockerfiles. A library installed manually in one container will not automatically be included in the next image.

## Related guides

- [PC setup](../guides/inglese/pc_setup.md): starting the environment, attaching VS Code and the first build.
- [Raspberry setup](../guides/inglese/raspberry_setup.md): initial installation, updates and enabling autostart.
- [ROS system startup](../guides/inglese/ros_system_startup.md): manual operation and checks on the boat.
- [Boat scripts](../DAY_BEFORE_REGATTA/README_ENG.md): roles and configuration of complete, quick, run and autostart.
