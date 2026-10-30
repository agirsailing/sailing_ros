# PC development environment setup

_Updated on: 30/10/2026_

[Italiano](../italiano/settaggio_pc.md)

This guide explains how to start Docker, open the repository,
create a container and attach VS Code. Install the [required software](software_necessary.md),
including extensions, and clone `sailing_ros` as described in the
[guide index](../README_ENG.md) first.

## 1. Start Docker Desktop and open the repository

1. Open **Docker Desktop** and wait for its engine to start. Use Linux containers on Windows.
2. Open **Visual Studio Code**.
3. Select **File > Open Folder…** and open your `sailing_ros` directory.

## 2. Open a PC terminal in the repository

Use **Git Bash on Windows** (included in Git for Windows) or **Terminal on macOS**.
In VS Code you can select the Git Bash profile from the terminal menu. Run these
commands on the PC, not inside the container or WSL. On Windows, if you
are not already in the repository:

```bash
cd "/c/Users/ettor/Desktop/Agir_Sailing_Team/sailing_ros"
```

On macOS use your clone's location, for example:

```bash
cd "$HOME/sailing_ros"
```

Replace paths with your computer's locations. Run the next commands from the
**sailing_ros root**, not ros2_ws.

## 3. Build and start the container

On Windows and macOS just run:

```bash
bash Docker/pc_container/build.sh
```

The script builds the image and creates or updates `agir-ros-pc` through Docker
Compose. Wait for the build to finish: the first run downloads ROS and dependencies.
Default startup requires no X server, GPU or host graphics configuration.
If you are already in `Docker/pc_container`, just run `bash build.sh`.
Run the same command again after changing the Dockerfile or Compose configuration.

**Optional graphics:** to open tools such as RViz, prepare and start a host X
server (for example VcXsrv on Windows or XQuartz on macOS), configured to accept
X11 connections over TCP from the container. Then run:

```bash
bash Docker/pc_container/build.sh --gui
```

This adds [compose.gui.yaml](../../Docker/pc_container/compose.gui.yaml) to the
[base Compose](../../Docker/pc_container/compose.yaml), using software rendering
without mounting a GPU. It does not install or configure the X server. The default
display is `host.docker.internal:0`; if your server uses another display, set it
for the command, for example `AGIR_DISPLAY=host.docker.internal:1 bash Docker/pc_container/build.sh --gui`.
To return to normal mode, run the script again without `--gui`.

If you created `agir-ros-pc` with the previous `docker run` command, Compose may
report a name conflict. Verify that it is the old container for this clone, stop
it with `docker stop agir-ros-pc`, then rename it with
`docker rename agir-ros-pc agir-ros-pc-previous` (choose an unused name) and run
`build.sh` again. The old container remains available for recovering files.

## 4. Check the container in Docker Desktop

Open **Containers** and find **`agir-ros-pc`**. Its state must be **Running**.
If stopped or Docker reported an error, inspect the terminal before continuing:
the name merely appearing in the list does not confirm startup.

## 5. Attach VS Code to the container

1. In the clone's VS Code window press **Ctrl+Shift+P** on Windows or **Cmd+Shift+P** on macOS.
2. Select **Dev Containers: Attach to Running Container…**.
3. Choose **`agir-ros-pc`**.
4. Wait for the new window attached to the container.

Dev Containers, included in Remote Development, provides this feature.
Reference: [official VS Code guide](https://code.visualstudio.com/docs/devcontainers/attach-container).

## 6. Open the workspace and build

In the **new window**, open `/home/ros/ros2_ws`, then **Terminal > New Terminal**.
This is now Bash **inside the container**, even on a Windows PC. Check:

```bash
pwd
```

The result must be `/home/ros/ros2_ws`. To compile:

```bash
bash scripts/build.sh --clean
source install/setup.bash
```

For communication launches first prepare `src/communication_web/config/mqtt_config.yaml`
from the template in that directory and configure both gateways. Tests with mocked
MQTT require no real credentials. Build, testing and arguments are explained in
the [scripts README](../../ros2_ws/scripts/README_ENG.md).

Both modes share `src`, `scripts`, `tools` and `rosbags` with the PC.
`build`, `install` and `log` stay inside the container: rebuild the workspace
after container recreation. Do not transfer these build products to the Raspberry.
Default networking supports outbound MQTT and ROS nodes within this container;
direct ROS communication with other computers requires dedicated network setup.
Stop the container from the PC terminal with `docker stop agir-ros-pc`.
To reuse it in the same mode, run `docker start agir-ros-pc` and attach VS Code
again. Use `build.sh` to update it or switch modes.
