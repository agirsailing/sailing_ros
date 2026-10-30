# Connecting to the Raspberry Pi

_Updated on: 30/10/2026_

[Italiano](../italiano/connessione_raspberry.md)

This guide explains how to access the Raspberry Pi over SSH and copy files between your computer and the device. To configure the Raspberry, start ROS or check the system, see [Raspberry Pi setup](raspberry_setup.md). A freshly flashed Raspberry contains the operating system, but not yet the repository or onboard software.

## Before connecting

Your computer must have an **SSH client** available: if it is missing, follow the [required software guide](software_necessary.md#1-ssh-from-the-terminal). SSH access must also be enabled on the Raspberry.

1. Make sure the Raspberry is powered on.
2. Connect the PC and Raspberry to the same Wi-Fi network or hotspot. Obtain its name and password from the team.
3. If `boat.local` does not resolve, use the Raspberry IP assigned by the router. Check that the hotspot allows communication between devices.

## SSH access

Open **CMD on Windows** or **Terminal with Bash on macOS** and run:

```text
ssh boat@boat.local
```

On the first connection, SSH may ask you to confirm the device's identity: verify the key fingerprint with your supervisor and answer `yes`.

When prompted for the `boat` user's password, enter the password provided by your supervisor. This is separate from the Wi-Fi password. No characters appear while you type it; this is normal.

After logging in, commands typed in that session run on the Raspberry. Use `exit` to disconnect and return to your computer.

### Changed device key warning

If a message like this appears before the password prompt:

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
Host key verification failed.
```

the device's key differs from the one saved on your computer. This can happen after reflashing the Raspberry. If your supervisor confirms the key change, remove the old entry from your computer's terminal:

```text
ssh-keygen -R boat.local
```

This command removes the key stored for `boat.local` from `known_hosts`, as described in the [OpenSSH manual](https://man.openbsd.org/ssh-keygen#R). Then connect again and confirm the verified new key:

```text
ssh boat@boat.local
```

If the change is unexpected, clarify it with your supervisor before removing the saved key.

## Copying files and folders

Run these commands **from your computer's terminal**, not from the SSH session on the Raspberry: open a second terminal or disconnect with `exit`.

`scp` copies data over SSH and may request the same `boat` user password. The `-r` option includes a folder and all its contents; it can be omitted for a single file. Reference: [scp manual](https://man.openbsd.org/scp).

### From the computer to the Raspberry

General form, replacing the paths and username:

```text
scp -r "pc_path_file" username@boat.local:path_raspberry
```

Example from CMD on Windows:

```cmd
scp -r "C:\Users\ettor\Desktop\Temp\script.sh" boat@boat.local:/home/boat
```

This command copies `script.sh` from your computer to the Raspberry's `/home/boat` folder. **It copies the file without executing it.**

### From the Raspberry to the computer

For example, to copy the rosbag folder to your PC from a Raspberry already configured with the project's paths:

```cmd
scp -r boat@boat.local:/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/rosbags/raw_recordings "C:\Users\ettor\Desktop\Temp"
```

This copies `raw_recordings` and its contents to `C:\Users\ettor\Desktop\Temp\raw_recordings`, leaving the originals on the Raspberry. Copy recordings that have already finished.

The destination folders in these examples must exist. Replace local paths with those on your computer; on macOS, use a local path such as `/Users/your_user/Desktop/Temp`. The remote rosbag path applies to the project installation described here and does not exist on a freshly flashed Raspberry.

To configure or start the ROS system, continue with [Raspberry Pi setup](raspberry_setup.md).
