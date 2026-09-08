# 🐳 ROS 2 Jazzy Docker Environment

This repository provides a fully containerized **ROS 2 Jazzy** development environment using **Docker**, **Docker Compose**, and a custom **entrypoint** script. It allows you to start developing ROS 2 packages easily on any machine, without worrying about local setup or dependencies.

## 📦 Overview

The container setup includes:

- A `Dockerfile` that builds a ROS 2 Jazzy base image.
- A `compose.yaml` file to run the container with optional shared volumes.
- An `entrypoint.sh` script that initializes the environment and passes commands correctly.

This is ideal for robotics development, CI setups, or cross-platform compatibility when using ROS 2.

For an overview of what docker is, how it works and why we use it, see the [Why Docker README](why_docker.md).

---

## 💻 Required Software for Development
To work efficiently with this ROS 2 Jazzy Docker-based framework, we recommend following the instructions in [Software Necessary README](software_necessary.md).

---

## 🚀 Getting Started

### 1. Build and Run the PC Container

This project provides a PC development image and a separate Raspberry Pi hardware image. Build and start the PC image using the provided helper script.

First, clone this repository locally:

```bash
git clone https://github.com/agirsailing/sailing_ros.git
```

Then move into the project root:

```bash
cd sailing_ros
```

Start Docker Desktop.

Now, from the repository root, build and start the PC container:

1. Open a terminal and run:

    ```bash
    cd Docker/pc_container
    bash build.sh
    ```

2. `build.sh` builds the Docker image and starts the container. The script is intended to mount `ros2_ws/` into the container so your workspace is available inside the running environment. Inspect `Docker/pc_container/build.sh` if you need to customize paths or options.

Notes:

- If you are on Windows, run the script from WSL, Git Bash, or a Bash-capable terminal. On PowerShell you may run the equivalent `bash build.sh` if Bash is available.
- The first build may take several minutes while base images and dependencies are downloaded. Subsequent runs will be faster thanks to Docker's layer cache.

If you prefer to use Docker Compose or want to customize mount points manually, see `Docker/pc_container/` for the generated compose snippets and the `Dockerfile` used by the build script.

### 2. Attach a VSCode window to the running container

Since you successfully ran `bash build.sh` in the previous step, your container is now running in the background. To connect your editor to it:

1. Open VSCode.
2. Using the extensions listed in the [Software Necessary README](software_necessary.md), you can connect to the container directly from VS Code using one of these two methods:

    - Method A: Command Palette. Press `Ctrl+Shift+P` (or `F1`/`Cmd+Shift+P` on Mac) to open the Command Palette. Search for *Dev Containers: Attach to Running Container*, press Enter and select your container (`agir-ros-pc`) from the dropdown list.
    - Method B: Docker Extension Panel. Click on the Docker icon, usually located on the left sidebar. Go to the Containers section, right-click on your running container, and select 'Attach Visual Studio Code'.

    
A new VSCode window will open automatically. You are now working directly inside the ROS2 container environment.

> **💡 Important Note for Future Runs**: The Docker engine relies on the Docker Desktop application. If you restart your computer and try to start the container or connect via VSCode, it will fail unless Docker Desktop is running in the background.
> To avoid manually opening the app every time, open Docker Desktop, go to Settings (Gear icon) > General, and check Start Docker Desktop when you log in. This ensures the Docker engine is always ready when you open VS Code.



### 3. Build the ROS 2 Workspace

With the container running and VS Code attached:

1. In the VS Code window, navigate to the ros2_ws/ folder inside the container.
2. Open a terminal (it should open in the workspace folder by default).
3. Run:
    ```bash
    cd scripts
    bash build.sh
    ```
    This script builds all ROS 2 packages in the workspace with the project defaults.
4. You can now start testing the software by running or launching nodes as needed.

The package is named `sensors`. Its launcher is `sensors_launch.py`:

```bash
bash /home/ros/ros2_ws/scripts/run.sh live
```

The launcher starts two ultrasonic nodes, their filter, GPS and battery monitoring.
It requires the connected hardware; the PC container is primarily for development.
The IMU executable is installed but is not part of this launcher yet.
The ultrasonic ports, topics and device IDs are configured in
`ros2_ws/src/sensors/config/params.yaml`, installed to `share/sensors/config/params.yaml`.
Rebuild the workspace after changing configuration to refresh the installed files.

### 4. Check the Graphical Interface (X Server)

The final step is to verify that the container can display graphical applications (e.g., rqt, rviz2) on your host computer.

To test this:

1. Make sure your host system is running an X Server (as provided in the [README](software_necessary.md))
2. In the container terminal, run a graphical command such as: `rqt`, `rqt_graph` or `rviz2`

On Windows/macOS, the default display is `host.docker.internal:0`; override `DISPLAY`
if your X server uses a different address. On Linux, enable the optional X11 socket
and Xauthority mounts in `pc_container/compose.yaml` if those paths exist. The GPU
mount is optional on PC. The Raspberry Pi configuration retains its Wayland, X11
and GPU mounts. Its Wayland socket target matches `/tmp/runtime-ros/wayland-0`.
Check that the host paths exist and that `/run/user/1000` matches the desktop user.

Both configurations use host networking for ROS discovery. Docker Desktop requires
enabling this under **Settings > Resources > Network > Enable host networking**;
see the [Docker host networking documentation](https://docs.docker.com/engine/network/drivers/host/).
Communication between the PC and Raspberry Pi still needs checking on the actual network.

### 5. Raspberry Pi Setup

The Raspberry Pi Compose file is `Docker/raspi_container/compose.yaml`. On the Pi,
enable I2C and connect the devices before starting the hardware container. If the
container user needs additional I2C/GPIO groups, uncomment their `group_add` entries
and set the actual numeric device group IDs in the terminal where you run Compose:

```bash
export I2C_GID=$(stat -c '%g' /dev/i2c-1)
export GPIO_GID=$(stat -c '%g' /dev/gpiochip0)
docker compose -f Docker/raspi_container/compose.yaml up -d --build
```

Run these commands from the repository root. You can also save those two numeric
values in `Docker/raspi_container/.env` when running Compose from that directory.
The hardware container is `agir-ros-raspi`; it exposes `/dev` for the existing serial,
I2C and GPIO code and retains privileged mode. Check serial device access through
the `dialout` group. The current GPS code expects `/dev/ttyUSB2`, and the battery
node expects `/dev/gpiochip0`. The original `/dev/ttyAMA0` device mapping is also
retained. Verify these and the graphical mount paths against the actual Pi.

The battery node's existing `sudo shutdown` call runs inside the container;
powering off the host Pi needs a separate host integration and is not implemented
by this Docker configuration.

### Workspace Paths and Dependencies

- Both Compose files resolve `../../ros2_ws` relative to their own directory.
  The PC mounts `src`, `scripts`, `rosbags`, `tools` and `CSVs` separately. The
  Raspberry Pi mounts the entire workspace under `/home/ros/ros2_ws`.
- On PC, build, install and log directories stay inside the container and are lost
  when it is recreated; rebuild afterward. On Raspberry Pi, these directories
  persist in its host checkout. CSVs and rosbags persist on both hosts.
- On Linux, ensure the mounted directories are writable by the container user
  (default UID/GID `1001`). Keep the username `ros`, since Compose and the entrypoint
  use `/home/ros`. Create the `ros2_ws/CSVs` folder as your host user before first use.
- The entrypoint loads ROS and, if available, the built workspace. A fresh container
  can open a shell before the first workspace build.
- The Dockerfiles install `rclpy`, message types, launch support, PySerial, SMBus2,
  lgpio and pyubx2. Optional Polimi ROS packages are commented out until needed.
  MQTT/Bluetooth Python integrations remain installed on Raspberry Pi and commented
  out on PC. Some ROS tools remain dependencies of the PC desktop base image.
- The Python package installs its launch and YAML files using `setup.py`, following
  the [ROS 2 package installation pattern](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-system.html).


## Workflow for Subsequent Sessions

The next time you want to work on your project, you don't need to rebuild the image. Just follow this quick routine:

1. Ensure the Docker Engine is running: Make sure the Docker Desktop app is open in the background. 

2. Start the container: You can wake up your existing container using one of three ways:

    * Directly from VSCode (Recommended): Open VS Code, go to the Docker extension, find your container under Containers, right-click it, and select Start.
    * From the Terminal: Open a terminal in your project folder (where compose.yaml is located) and run:

        ```docker compose start```
    * From Docker Desktop: In the Containers section of Docker Desktop, select Start ("play" button) on your container.

3. Attach VS Code: Once the container is running, use `Ctrl+Shift+P` to attach to it.
