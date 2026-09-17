# Agir Raspberry Pi 4 preparation

These templates target Raspberry Pi 4 with a 64-bit Debian/Ubuntu-based OS and
the desktop user `agir`. The default checkout is
`/home/agir/2025_SOFTWARE/sailing_ros`. Run setup/update as that user, without
prefixing the whole script with sudo; individual administrative steps use sudo.
The exact OS release and hardware identities still need confirmation on the Pi.

## First setup

Fill `GIT_USER` and `GIT_TOKEN` in a local copy of
`script_setup_rasp4_template.sh`, then run that copy. The script:

1. Checks the board, 64-bit architecture, user and boot configuration path.
2. Stops an existing regatta service and container before changing the system.
3. Installs host tools, enables SSH, configures I2C and hardware permissions.
4. Installs/checks Docker and the modern `docker compose` plugin.
5. Clones or resets the checkout to `origin/main`, retaining the existing policy
   that the Pi has no local edits to tracked files.
6. Builds the image and a clean ROS workspace, then leaves the system stopped.

Reboot after setup to activate I2C and the desktop user's Docker group membership.
The script prepares USB serial permissions for two ultrasonic sensors and GPS,
I2C for the IMU/compass multiplexer, and GPIO for the battery alarm. It does not
configure an STM32 serial link, force UART baud rates, disable Bluetooth, scan
I2C addresses or select multiplexer channels. The sensor node owns the mux.

Both `/boot/firmware/config.txt` and `/boot/config.txt` are supported. A managed
`[all]` block enables `i2c_arm`; `i2c-dev` is configured to load at boot. Existing
serial/GPIO/I2C rules use the same `0666` policy as the original template; the
workspace retains `chmod 777` as requested.

The current `/dev/ttyUSB0`, `/dev/ttyUSB1`, `/dev/ttyUSB2` assignments in
`sensors/config/params.yaml` are provisional. Once the real adapters are known,
set their stable `/dev/serial/by-id/...` paths (if uniquely identifiable), or
install rules based on the actual devices/physical ports. Do not invent adapter
identities in this template. Confirm I2C bus/channel/address and GPIO chip/line
against the wiring; their values remain in the sensor YAML.

## Updating an already prepared Pi

`script_quick_setup_template.sh` works on the prepared Pi 4. It stops the regatta
service **before** stopping the container, pulls code, and always evaluates the
Docker build using cached layers. It then starts the updated container and runs
`build.sh --incremental`, retaining `build`, `install` and `log`.

The successful build's image ID is recorded in `ros2_ws/build/.agir_image_id`.
If that ID differs or the record is missing, it selects a clean ROS build because
dependencies may have changed. Failed builds do not advance this record.
Pass `--clean` explicitly after deleting/renaming packages or when
you need a complete rebuild. Running `build.sh` without arguments still defaults
to a clean build for compatibility.

Both full setup and quick update leave ROS and the regatta service stopped. A
failed build also stops the build container. Boot enablement is preserved; an
explicit `systemctl stop` is not undone by `Restart=always`. Do not start the
service manually or reboot during an update. After successful compilation,
restart the installed service with `sudo systemctl start agir_regatta.service`,
or run `agir_regatta_start.sh` if no service has been installed.

If the boot script was previously installed in `/usr/local/bin`, setup/update
refresh that copy after a successful build. They do not install a new service.
Both use the Compose container name `agir-ros-raspi`.

## Wi-Fi and automatic startup

These remain separate installation steps:

- Fill the Wi-Fi SSID, password and connection-profile placeholders in
  `agir_wifi_check.sh`, then run `install_wifi_guardian.sh` with sudo from this
  directory. It installs, enables and immediately runs the Wi-Fi guardian. It
  requires NetworkManager. The check runs once per boot, not continuously.
- Run `setup_service_boot.sh` with sudo from this directory after the system has
  been prepared and rebooted. It installs, enables and immediately starts the
  regatta service. It currently writes the service definition itself, rather than
  copying the checked-in `.service` file.

`agir_regatta_start.sh` intentionally waits for a successful ping to `8.8.8.8`
before starting ROS, as requested. It still requires working Internet/ICMP.
Starting the live launcher starts rosbag_manager but does not start recording;
recording begins when a start request is received.

## Desktop and boot prerequisites

The graphical Compose mounts are retained. Having a desktop OS installed does
not guarantee that a Wayland session exists when a system service starts:
confirm the actual desktop user ID, `wayland-0` socket and Xauthority path. The
current paths assume `/run/user/1000/wayland-0` and the user's `~/.Xauthority`.
Setup/update preserve the user's HOME when invoking Compose through sudo.

ROS sensor acquisition itself does not need a graphical login. If these mounts
cause boot problems, separate optional graphical access from the boot Compose
configuration; this change has not been made here.

Configure the MQTT broker in `communication_web/config/mqtt_config.yaml` before the
regatta. Wi-Fi credentials, Git credentials, broker details and adapter identities
are deployment values to be decided; placeholders are deliberate.

## Validation scope

Changes are checked offline only. No Docker operation, ROS build, network setup
or access to real Raspberry Pi hardware is performed during code review. The
first deployment must verify the chosen OS, boot-time GUI paths and actual sensor
connections.
