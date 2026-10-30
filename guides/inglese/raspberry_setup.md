# Raspberry Pi setup and updates

_Updated on: 30/10/2026_

[Italiano](../italiano/settaggio_raspberry.md) · [Guides](../README_ENG.md)

This guide covers two cases:

1. **A freshly flashed Raspberry:** initial installation and configuration of the onboard system.
2. **An already configured Raspberry:** code updates and rebuilding.

**Autostart**, which starts ROS automatically when the Raspberry boots, is enabled separately in the final section, after manual testing. The entire procedure uses SSH: no screen, keyboard or open desktop session is needed on the Raspberry.

## Before you start

Install the [required software](software_necessary.md) on your PC and clone the repository as described in the [guide index](../README_ENG.md).

The commands use the `boat` account, hostname `boat.local`, and repository path `/home/boat/2025_SOFTWARE/sailing_ros` on the Raspberry. Scripts download code from the `main` branch on GitHub: make sure the changes you want to install are already on that branch.

Prepare networking and SSH access using the [connection guide](raspberry_connection.md). The Raspberry needs Internet access to download code, images and dependencies. Run the Raspberry scripts as `boat`, without prefixing them with `sudo`: they request administrative privileges when needed. The exception is the autostart installer, whose command with `sudo` is shown at the end.

## Case 1 — Freshly flashed Raspberry

### 1. Prepare the operating system

Use Raspberry Pi Imager to install the **64-bit Raspberry Pi 4 operating system** specified by the person responsible for the system.

During preparation, configure user `boat`, hostname `boat`, the password provided by your team, the team network and SSH access. Start the Raspberry and check that you can connect using the [connection guide](raspberry_connection.md).

### 2. Prepare a private copy of repository.sh on the PC

Copy [`DAY_BEFORE_REGATTA/steps/repository.sh`](../../DAY_BEFORE_REGATTA/steps/repository.sh) into a PC directory **outside the repository**. For example, from the `sailing_ros` root:

**Windows — CMD:**

```cmd
copy "DAY_BEFORE_REGATTA\steps\repository.sh" "%USERPROFILE%\repository.sh"
```

**macOS — Bash:**

```bash
cp DAY_BEFORE_REGATTA/steps/repository.sh "$HOME/repository.sh"
```

Open the copy in VS Code. In the `repository_configure()` function, replace these two lines:

```bash
GIT_USER="${AGIR_GIT_USER:-${GIT_USER:-}}"
GIT_TOKEN="${AGIR_GIT_TOKEN:-${GIT_TOKEN:-}}"
```

with the values provided by your team, replacing the example placeholders:

```bash
GIT_USER='USERNAME_PROVIDED_BY_YOUR_TEAM'
GIT_TOKEN='TOKEN_PROVIDED_BY_YOUR_TEAM'
```

`GIT_TOKEN` is the GitHub access token. Keep the other parameters unchanged, including branch `main`. Save the file with **LF** line endings: you can select them in the VS Code status bar.

Credentials belong only in the private copy, not in the original repository file. The script does not ask for them in the terminal. If they are missing, it stops and tells you which file to complete; if authentication is rejected, it displays **“Errore nel token.”** (token error).

### 3. Transfer and run repository.sh

From the **PC terminal**, copy the file into the `boat` home directory.

**Windows — CMD:**

```cmd
scp "%USERPROFILE%\repository.sh" boat@boat.local:/home/boat/repository.sh
```

**macOS — Bash:**

```bash
scp "$HOME/repository.sh" boat@boat.local:/home/boat/repository.sh
```

If you chose another directory for the private copy, adjust the local path. Then connect from the PC:

```text
ssh boat@boat.local
```

Now, in the **Raspberry SSH terminal**, run the script without `sudo` or arguments:

```bash
bash /home/boat/repository.sh
```

The script installs Git if needed, downloads the repository and saves the branch and paths in `DAY_BEFORE_REGATTA/config.local.sh`. It does not launch the complete setup: the MQTT configuration must be copied first.

Wait for `Repository ready in /home/boat/2025_SOFTWARE/sailing_ros.` before continuing.

If you saved the copy with Windows line endings (CRLF) and Bash reports errors containing `\r`, fix the file on the Raspberry and run it again:

```bash
sed -i 's/\r$//' /home/boat/repository.sh
bash /home/boat/repository.sh
```

This is unnecessary if the file already uses LF. Clone credentials may remain in the `origin` URL in the local Git configuration: do not share `.git/config` or `git remote -v` output with the token visible.

### 4. Copy the MQTT configuration

After downloading the repository, copy the web app communication configuration from the PC:

| File | Purpose | Destination on the Raspberry |
|---|---|---|
| `mqtt_config.yaml` | Broker address and MQTT credentials for the ROS gateways. | `/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml` |

Ask your team for the completed file. If you need to prepare it, start from [`mqtt_config.example.yaml`](../../ros2_ws/src/communication_web/config/mqtt_config.example.yaml) and fill in both gateway sections. Use the broker's TCP/TLS hostname and port; do not put the browser's `wss://` URL in the host field. MQTT credentials are different from the GitHub token.

Open **a second terminal on the PC**, at the `sailing_ros` root, keeping the SSH session open. With the file in the local `ros2_ws/src/communication_web/config/` directory, run the same command on Windows and macOS:

```text
scp ros2_ws/src/communication_web/config/mqtt_config.yaml boat@boat.local:/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml
```

### 5. Run the complete setup

Return to the **Raspberry SSH terminal** and run [`complete_setup.sh`](../../DAY_BEFORE_REGATTA/complete_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/complete_setup.sh
```

The script configures the system, hardware connections and Docker, updates code from the selected branch and builds the ROS workspace. It is intended for initial installation: it resets tracked files to the remote branch, discarding local changes, and recreates the build outputs.

It also configures stable USB device names and the IMU UART. Git is configured to ignore executable-bit changes (`core.fileMode=false`); repository line endings are managed by `.gitattributes`.

Wait for the script to finish without errors and display `SETUP FINISHED! The system is ready but STOPPED.`. The system has been built, but ROS remains stopped: autostart is not installed.

### 6. Reboot and test manually

Once setup has completed, run on the Raspberry:

```bash
sudo reboot
```

The SSH session closes. Rebooting applies the I2C/UART changes and user-group membership. Wait for the Raspberry to restart, then reconnect **from the PC**:

```text
ssh boat@boat.local
```

In the **Raspberry SSH terminal**, check that the connected sensor ports and container are available:

```bash
ls -l /dev/ultrasonic_left /dev/ultrasonic_right /dev/gps /dev/ttyAMA0 /dev/i2c-1
docker compose version
docker ps -a --filter name=agir-ros-raspi
```

USB names depend on the assigned physical ports: left `1-1.4:1.0`, right `1-1.3:1.0`, GPS `1-1.2:1.0`. The BNO085 IMU instead uses UART `/dev/ttyAMA0` on GPIO14/15; setup disables Bluetooth and the serial console to dedicate this port to it. If a device is missing, check its connection before starting the nodes.

Continue with the [ROS startup guide](ros_system_startup.md), starting with manual operation. Check sensor data and web app communication before enabling autostart.

## Case 2 — Updating an already configured Raspberry

This procedure downloads code from `main` on GitHub and rebuilds the system. Changes to deploy must therefore already be on that branch.

Connect **from the PC**:

```text
ssh boat@boat.local
```

In the **Raspberry SSH terminal**, run [`quick_setup.sh`](../../DAY_BEFORE_REGATTA/quick_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/quick_setup.sh
```

The script stops the ROS service and container, updates code and rebuilds. Wait for it to finish without errors. The existing MQTT file and local settings are preserved: you do not need to copy them again for a normal update. Saved Git credentials are also reused; to replace them, fill `AGIR_GIT_USER` and `AGIR_GIT_TOKEN` in `DAY_BEFORE_REGATTA/config.local.sh`.

If ROS messages changed or packages were removed or renamed, use `bash DAY_BEFORE_REGATTA/quick_setup.sh --clean` instead of the normal command.

ROS remains stopped when the script finishes. Follow the [startup guide](ros_system_startup.md) to restart it, depending on whether autostart is enabled.

## Enabling autostart

After successful manual testing, interrupt the run with `Ctrl+C`. In the **Raspberry SSH terminal**, run [`autostart_setup.sh`](../../DAY_BEFORE_REGATTA/autostart_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
sudo bash DAY_BEFORE_REGATTA/autostart_setup.sh
```

The script stops any processes left from manual testing, installs **`agir_regatta.service`**, enables it for future boots and **starts ROS immediately**. Complete and quick setup do not invoke it, and no desktop session is required.

To disable automatic startup and stop the current container as well:

```bash
sudo systemctl disable --now agir_regatta.service
docker stop agir-ros-raspi
```

For more detail about each script, see the [DAY_BEFORE_REGATTA README](../../DAY_BEFORE_REGATTA/README_ENG.md).
