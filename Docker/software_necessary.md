# 💻 Required Software for Development

To work efficiently with this ROS 2 Jazzy Docker-based framework, we recommend installing the following tools depending on your operating system:

---

## 🐙 Git & GitHub Desktop

**Purpose:** Version control system to manage source code, track changes, and collaborate with others.

- [Download GitHub Desktop](https://desktop.github.com/download/)

GitHub Desktop provides a graphical interface to work with repositories and branches. **However, it's not available on Ubuntu/Linux.**

🔧 **For Ubuntu/Linux**: Install and use Git via the command line:

- [Install Git on Linux](https://git-scm.com/downloads/linux)

---

## 🐳 Docker

**Purpose:** Containerization tool to ensure a consistent development environment across all machines.

- [Docker Desktop (Recommended for macOS/Windows)](https://www.docker.com/products/docker-desktop/)

> Docker enables ROS to run inside a containerized environment, isolating dependencies and matching the system across all devices.

🔧 **Linux Users**:

- **Option 1 – Clean CLI installation** *(recommended for performance)*:
  - [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- **Option 2 – Docker Desktop for Linux** *(easier, GUI included)*:
  - [Docker Desktop for Linux](https://docs.docker.com/desktop/install/linux/)

---

## 🧠 Visual Studio Code (VS Code)

**Purpose:** Unified development environment to edit, debug, and manage code in both host and container machines.

- [Download VS Code](https://code.visualstudio.com/download)

**Features:**
- Connect to remote machines via SSH
- Open and develop inside Docker containers
- Integrate Git and Docker inside the editor
- Highlight and check syntax in real-time

📦 **Recommended Extensions:**

| Extension | Purpose | Install |
|----------|---------|---------|
| Git Extension Pack | Git management tools | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=donjayamanne.git-extension-pack) |
| Docker Extension | Docker container/file/browser support | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=formulahendry.docker-extension-pack) |
| Remote Development | Connect to containers or SSH | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) |
| C++ Extension Pack | Linting, IntelliSense for C++ | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools-extension-pack) |
| Python Extension Pack | Python dev tools | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=donjayamanne.python-extension-pack) |
| ROS Extension | ROS integration & launch file support | [🔗 Link](https://marketplace.visualstudio.com/items?itemName=ms-iot.vscode-ros) |

---

## 🪟 X Server (Optional but Useful)

**Purpose:** Enables graphical applications inside Docker containers (e.g., `rviz2`, `rqt`) to display on your local screen.

| Platform | Tool | Link |
|----------|------|------|
| Windows | VcXsrv | [🔗 Download](https://sourceforge.net/projects/vcxsrv/) |
| macOS   | XQuartz | [🔗 Download](https://www.xquartz.org/) |

Make sure to allow connections from your Docker container to the X server.

---

## 🔐 Remote Connection Tools (SSH)

For smooth and stable development on Raspberry Pi or remote machines:

> Note: The **VS Code Server** runs on the Raspberry Pi to enable remote editing, but it consumes considerable RAM and **should not be used while the software is running**. A plain SSH connection is always preferable when running the actual code.

| Platform | Recommended Tool | Link |
|----------|------------------|------|
| **Windows** | MobaXterm | [🔗 Download](https://mobaxterm.mobatek.net/) |
| **macOS** | Termius | [🔗 Download](https://termius.com/download/macos) |
| **Ubuntu** | Native terminal | Just use the terminal and store your `ssh user@host` commands for reuse. |

---

With these tools installed and configured, you’ll be able to develop ROS 2 packages inside Docker containers, sync files with Git, visualize ROS apps on your host, and connect remotely to the onboard computer when needed.
