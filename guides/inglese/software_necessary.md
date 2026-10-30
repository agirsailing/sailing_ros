# Required software

_Updated on: 30/10/2026_

[Italiano](../italiano/software_necessari.md)

This guide lists the software to install on your computer to work on the repository. The instructions cover **Windows** and **macOS**.

All members must have **terminal SSH access, Git, GitHub Desktop, Docker Desktop and Visual Studio Code with the extensions listed below**. X servers and additional remote connection applications are optional.

## Mandatory software

### 1. SSH from the terminal

SSH lets you connect to the Raspberry Pi and run commands remotely. Your computer needs the **OpenSSH client**. If it is already available, you do not need to reinstall it.

#### Windows: Command Prompt (CMD)

Open **Command Prompt** by searching for `cmd` in the Start menu, then run:

```cmd
ssh -V
```

If the OpenSSH version appears, the client is available. If the command is not recognized, open Windows **Optional features** and add **OpenSSH Client**, following the [official Microsoft guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse). Connecting to the Raspberry only requires the client; you do not need to install OpenSSH Server on your PC.

After installation, reopen CMD and run `ssh -V` again. Use CMD for connections to the Raspberry.

#### macOS: Terminal with Bash

Open the **Terminal** app and start Bash:

```bash
/bin/bash
```

Then check that SSH is available:

```bash
ssh -V
```

The SSH client is already available on macOS. For remote connections, see the [official Apple guide](https://support.apple.com/guide/terminal/trml1018/mac). Starting Bash this way applies to the current session and does not require changing the Mac's default shell.

### 2. Git and GitHub Desktop

Install **both**:

- **Git** manages code versions and lets you run commands such as `git clone` from the terminal.
- **GitHub Desktop** provides a graphical interface for repositories, branches, commits and synchronization with GitHub.

| Software | Windows | macOS |
|---|---|---|
| Git | [Download and installation](https://git-scm.com/install/windows) | [Official installation guide](https://git-scm.com/install/mac) |
| GitHub Desktop | [Download](https://desktop.github.com/download/) | [Download](https://desktop.github.com/download/) |

On macOS, you can install Git through Xcode Command Line Tools, as described in the official guide:

```bash
xcode-select --install
```

After installation, reopen CMD or Terminal and check:

```text
git --version
```

Then open GitHub Desktop and sign in with your GitHub account.

### 3. Docker Desktop

Docker Desktop runs the project's ROS 2 environment in a container with the dependencies needed for development.

| System | Download and installation guide |
|---|---|
| Windows | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| macOS | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |

On Windows, also follow the **WSL 2** requirements and instructions in the Docker guide. On Mac, choose the download for your processor: **Apple silicon** or **Intel**.

After installation, open Docker Desktop and wait for the Docker engine to start. Project environment configuration is covered in the [PC setup guide](pc_setup.md).

### 4. Visual Studio Code and its extensions

Install [Visual Studio Code from the official website](https://code.visualstudio.com/download). We use it to edit code, debug and work inside the ROS container.

Open the **Extensions** view in VS Code and install every extension in the table. The links point to their Visual Studio Marketplace pages.

| Extension | Purpose | Installation |
|---|---|---|
| Git Extension Pack | Tools for Git history and repository management. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=donjayamanne.git-extension-pack) |
| Docker Extension Pack | Management of containers, images and Docker files. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=formulahendry.docker-extension-pack) |
| Remote Development | Development inside containers and connections to remote machines over SSH. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) |
| C/C++ Extension Pack | Code completion, debugging and C/C++ tools. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools-extension-pack) |
| Python Extension Pack | Tools for writing, checking and debugging Python code. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=donjayamanne.python-extension-pack) |
| ROS | Support for ROS files, messages and URDF/Xacro models. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-iot.vscode-ros) |

The **Remote Development** pack includes **Dev Containers**, for working inside the container, and **Remote - SSH**, for connecting the editor to a remote machine.

## Optional software

### X server

An X server displays windows from graphical applications running inside the container, such as `rviz2` and `rqt`, on your computer.

| System | Software | Download |
|---|---|---|
| Windows | VcXsrv | [Official project releases](https://github.com/marchaesen/vcxsrv/releases) |
| macOS | XQuartz | [Official website](https://www.xquartz.org/) |

Graphical applications also require the container-to-X-server connection to be configured. For the graphics connections defined by the project, see the [Docker README](../../Docker/README_ENG.md).

### Remote connection tools

These applications provide an interface for saving and managing SSH connections. They are optional: the terminal connection described above remains the standard method.

| System | Software | Download |
|---|---|---|
| Windows | MobaXterm | [Official website](https://mobaxterm.mobatek.net/download.html) |
| macOS | Termius | [Official website](https://termius.com/download/macos) |

While the onboard software is running, use a regular terminal SSH session and close VS Code Remote - SSH sessions connected to the Raspberry to leave the device's resources available to the ROS system.

[Back to guides](../README_ENG.md)
