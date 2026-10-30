# Starting the ROS system on the Raspberry Pi

_Updated on: 30/10/2026_

[Italiano](../italiano/avvio_sistema_ros.md)

This guide explains how to start the ROS system on the Raspberry Pi and use a few commands to check its operation.

It assumes that the code is already on the Raspberry and that configuration has been completed following the [Raspberry setup guide](raspberry_setup.md).

There are two startup cases: **autostart disabled**, requiring manual startup, or **autostart enabled**, with automatic startup when the Raspberry boots.

## Check the autostart status

From your PC terminal, connect to the Raspberry following the [connection guide](raspberry_connection.md):

```text
ssh boat@boat.local
```

In the **Raspberry SSH terminal**, check whether the service is enabled at boot:

```bash
systemctl is-enabled agir_regatta.service
```

- `enabled`: autostart is enabled.
- `disabled`: the service is installed, but autostart is disabled.
- `not-found` or a message stating that the service does not exist: autostart is not installed; use manual startup.

If you see `masked` or another error, check the service configuration before proceeding.

If the service is installed, also check whether it is currently running:

```bash
systemctl is-active agir_regatta.service
```

`active` means the service is running, `inactive` means it is stopped, and `failed` means an error has occurred. Boot enablement and current status are separate: a service can be enabled but stopped, or disabled but still running.

If the service is already `active`, proceed to the debugging commands without starting a second instance of the system. The `active` status alone does not guarantee that all ROS nodes are ready.

## Case 1 — Autostart disabled

To start the system manually, in the **Raspberry SSH terminal**, enter the `DAY_BEFORE_REGATTA` folder, make [`run.sh`](../../DAY_BEFORE_REGATTA/run.sh) executable and run it:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros/DAY_BEFORE_REGATTA
chmod +x run.sh
./run.sh
```

The script starts the **`agir-ros-raspi`** container and the ROS system inside it. Keep this terminal open to follow messages during execution; use a second terminal for checks.

At startup, the script waits until the Raspberry can reach `8.8.8.8` via ping, unless configured otherwise. If it stays on the network waiting message, check that the Raspberry has Internet access and that ping is not blocked.

## Case 2 — Autostart enabled

If autostart is enabled, ROS starts automatically when the Raspberry boots through **`agir_regatta.service`**. There is no need to run `run.sh` manually.

You can check the service status from the **Raspberry SSH terminal**:

```bash
systemctl status agir_regatta.service --no-pager
```

Automatic startup also waits for the network, as described in the manual case.

If the service is stopped, for example after an update with `quick_setup.sh`, start it without rebooting the Raspberry:

```bash
sudo systemctl start agir_regatta.service
```

To enable autostart, follow the dedicated section in the [Raspberry setup guide](raspberry_setup.md#enabling-autostart).

## Useful debugging commands

Open **another terminal on your PC** and connect to the Raspberry in a second SSH session:

```text
ssh boat@boat.local
```

### List running containers

In the **Raspberry SSH terminal**:

```bash
docker ps
```

Look for `agir-ros-raspi` in the `NAMES` column. Its presence indicates that the container is running; use the following commands to check ROS.

### Enter the container

Open a shell inside the running container:

```bash
docker exec -it agir-ros-raspi bash
```

From this point on, commands run **inside the container**. Load the ROS environment and workspace:

```bash
source /opt/ros/jazzy/setup.bash
source /home/ros/ros2_ws/install/setup.bash
```

### List ROS nodes

```bash
ros2 node list
```

Shows the ROS nodes visible in the session.

### List ROS topics

```bash
ros2 topic list
```

Shows the available ROS topics.

### Read messages from a topic

```bash
ros2 topic echo <topic_name>
```

Replace `<topic_name>`, including the angle brackets, with a name returned by `ros2 topic list`. The command displays messages as they are published. Press `Ctrl+C` to stop reading.

To leave the container shell and return to the Raspberry terminal, run `exit`: this does not stop the ROS system.

### Read autostart logs

If the system was started through the service, from the **Raspberry SSH terminal, outside the container**, you can read the latest messages and follow new ones:

```bash
sudo journalctl -u agir_regatta.service -n 100 -f
```

Press `Ctrl+C` to stop viewing the logs.


### Read a measurement and check its rate

Inside the container:

```bash
ros2 topic echo /ultrasonic/left --field range
```

Stop with Ctrl+C, then try:

```bash
ros2 topic hz /imu/data
```

To stop the system, first stop recording through the webapp or ROS service.
Then, on the Raspberry host from the repository root:

```bash
sudo systemctl stop agir_regatta.service
docker compose -f Docker/raspi_container/compose.yaml stop
```

The first command is only needed when the service is installed. Closing SSH or
exiting the container does not guarantee that ROS processes stop.
