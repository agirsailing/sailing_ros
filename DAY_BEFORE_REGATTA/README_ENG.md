# Raspberry installation, updates and startup

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../README_ENG.md)

Scripts are split by responsibility. For a fresh Raspberry follow the
[complete SSH procedure](../guides/inglese/raspberry_setup.md), which distinguishes
files to copy and commands on the PC, Pi host and container. Do not execute every
line on this reference page as one procedure.

## Entry points

| Script | Run on Pi host | Effect |
|---|---|---|
| [steps/repository.sh](steps/repository.sh) | `bash /home/boat/repository.sh` on a private copy | No-argument bootstrap: retrieves the repository and creates local configuration if missing |
| [complete_setup.sh](complete_setup.sh) | `bash complete_setup.sh` as boat | Configures host/hardware/Docker; repository full, cleanup and complete build; leaves runtime stopped |
| [quick_setup.sh](quick_setup.sh) | `bash quick_setup.sh` or `bash quick_setup.sh --clean` | Updates repository/image and builds; leaves runtime stopped |
| [run.sh](run.sh) | `bash run.sh` | Waits for network, starts container and live system |
| [autostart_setup.sh](autostart_setup.sh) | `sudo bash autostart_setup.sh` | Installs, enables **and immediately starts** `agir_regatta.service` |
| [network/install_wifi_guardian.sh](network/install_wifi_guardian.sh) | Separate optional installation | Installs a Wi-Fi profile check at boot |

Run main scripts from this directory. Complete/quick do not install autostart:
do that manually after testing. Do not run complete/quick/run with `sudo`;
individual steps request privileges when required.

## Local configuration

[config.example.sh](config.example.sh) documents variables; `config.local.sh` is
private and ignored by Git. Defaults: user `boat`, home `/home/boat`, repository
`/home/boat/2025_SOFTWARE/sailing_ros`, branch `main`. Set `AGIR_BRANCH`
deliberately; quick updates the current checkout and is not a branch switch.
`AGIR_TARGET_IP` changes the startup network ping target (default `8.8.8.8`).
A reachable router can be more suitable without Internet.

Git and MQTT have different credentials. `repository.sh` reuses the available
Git origin/helper, or applies an explicitly configured credential pair.
It never asks for username/token in the terminal and disables authentication dialogs.
Missing HTTPS credentials stop the script: fill `GIT_USER` and `GIT_TOKEN` in
the private copy of `repository.sh`, or `AGIR_GIT_USER` and `AGIR_GIT_TOKEN` in
`config.local.sh`. Authentication rejection stops the script with
**“Errore nel token.”** (token error), without assuming expiry is the cause.
Other Git/network errors have a separate message. This applies to bootstrap,
`full` and `update`; quick also accepts replacement credentials from the local file.
Existing SSH origins use available keys without prompting.
A token may be in the origin URL: never share remote/config output. Do not commit
copies containing secrets.

## Repository full and update

`full` resets tracked files to the remote branch: preserve any needed changes
elsewhere first. `update` uses pull with rebase/autostash. Both set
`core.fileMode=false`, ignoring executable-bit changes in status. The scripts
currently apply `chmod -R 777` to the workspace. `.gitattributes` manages line
endings, independently of permissions. `sed -i 's/\r$//'` is only needed when
the bootstrap copy has CRLF endings.

Quick rebuilds the image with cache; it cleans the workspace build when the
image changes or with `--clean`, otherwise builds incrementally. After setup
script changes, check the checkout before running them: functions are loaded
at startup, before the internal Git update.

## Modules and hardware

| File | Responsibility |
|---|---|
| [lib/common.sh](lib/common.sh) | Shared configuration, checks and step loading |
| [steps/host.sh](steps/host.sh) | Host preparation |
| [steps/hardware.sh](steps/hardware.sh) | I2C, UART, udev rules and device permissions |
| [steps/docker.sh](steps/docker.sh) | Docker installation/configuration |
| [steps/repository.sh](steps/repository.sh) | Bootstrap, full/update and workspace permissions |
| [steps/workspace.sh](steps/workspace.sh) | Cleanup and container compilation |
| [steps/runtime.sh](steps/runtime.sh) | Stopping, container handling and startup link |

Udev maps `/dev/ultrasonic_left` to USB port `1-1.4:1.0`,
`/dev/ultrasonic_right` to `1-1.3:1.0`, and `/dev/gps` to `1-1.2:1.0`.
Changing sockets/hubs can change these paths. BNO085 uses `/dev/ttyAMA0`:
hardware setup enables UART and removes the serial console, requiring a reboot.

## Starting and stopping

Run waits indefinitely for ping before starting ROS. This does not verify MQTT
credentials. Closing SSH does not guarantee that the container process stops.
First close any recording, then stop the service if active and the container:

```bash
sudo systemctl stop agir_regatta.service
cd /home/boat/2025_SOFTWARE/sailing_ros
docker compose -f Docker/raspi_container/compose.yaml stop
```

The first command is only needed if the service is installed. To return to manual
operation permanently use `sudo systemctl disable --now agir_regatta.service`.
Autostart logs: `journalctl -u agir_regatta.service -b`.
