#!/usr/bin/env bash
set -euo pipefail

echo "AGIR RASPBERRY PI 4 SETUP — USB sensors, I2C, GPIO and ROS"

########################################
# ⚙️  PARAMETERS TO ADAPT
########################################

USER_HOME="/home/agir"
BASE_DIR="$USER_HOME/2025_SOFTWARE"

GIT_USER="INSERT_GITHUB_USERNAME"
GIT_TOKEN="INSERT_GITHUB_TOKEN"
REPO_SLUG="agirsailing/sailing_ros"

REPO_DIR="$BASE_DIR/sailing_ros"
BRANCH="main"

ROS_WS="$REPO_DIR/ros2_ws"
CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="agir-ros-raspi"
IMAGE_NAME="agirsailing:jazzy-raspi"
REGATTA_SERVICE="agir_regatta.service"

# Run as the desktop user, not with sudo bash: individual privileged steps use sudo.
if [[ "$EUID" -eq 0 || "$HOME" != "$USER_HOME" ]]; then
  echo "Run this script as the user whose home is $USER_HOME."
  exit 1
fi
if [[ -z "$GIT_USER" || "$GIT_USER" == INSERT_* || -z "$GIT_TOKEN" || "$GIT_TOKEN" == INSERT_* ]]; then
  echo "Fill the GitHub username/token placeholders before running setup."
  exit 1
fi
if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "This setup requires a 64-bit ARM operating system."
  exit 1
fi
MODEL="$(tr -d '\0' < /proc/device-tree/model)"
if [[ "$MODEL" != *"Raspberry Pi 4"* ]]; then
  echo "This setup targets Raspberry Pi 4; detected: $MODEL"
  exit 1
fi
if [[ -f /boot/firmware/config.txt ]]; then
  BOOT_CONFIG=/boot/firmware/config.txt
elif [[ -f /boot/config.txt ]]; then
  BOOT_CONFIG=/boot/config.txt
else
  echo "Cannot find Raspberry Pi boot configuration."
  exit 1
fi

# An explicit systemctl stop suppresses Restart=always without disabling boot startup.
if systemctl cat "$REGATTA_SERVICE" >/dev/null 2>&1; then
  sudo systemctl stop "$REGATTA_SERVICE"
fi
# Stopping the docker exec client alone does not guarantee that ROS has stopped.
if command -v docker >/dev/null 2>&1 && sudo docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  sudo docker stop "$CONTAINER_NAME"
fi

########################################

echo "🔎 Current user: $USER"
echo "📁 BASE_DIR:   $BASE_DIR"
echo "📁 REPO_DIR:   $REPO_DIR"
echo "🌿 Branch:     $BRANCH"

########################################
# 0) Fix hosts/hostname (optional but useful)
########################################

HOSTN="$(hostnamectl --static || hostname)"
if ! grep -q "^127\.0\.1\.1\s\+$HOSTN" /etc/hosts; then
  echo "🔧 Aligning /etc/hosts with hostname: $HOSTN"
  if grep -q "^127\.0\.1\.1" /etc/hosts; then
    sudo sed -i "s/^127\.0\.1\.1.*/127.0.1.1   $HOSTN/" /etc/hosts
  else
    echo "127.0.1.1   $HOSTN" | sudo tee -a /etc/hosts >/dev/null
  fi
fi

########################################
# 1) Update & base packages
########################################

echo "🔄 Update & upgrade..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "📦 Installing base packages (SSH, git, curl, nano, tree, ca-certificates, lsb-release)..."
sudo apt-get install -y \
  openssh-client openssh-server \
  git curl nano tree ca-certificates lsb-release i2c-tools gpiod

echo "📡 Enabling SSH server..."
sudo systemctl enable ssh
sudo systemctl start ssh

########################################
# 1.5) Agir hardware: enable I2C and grant USB serial / I2C / GPIO access
########################################

echo "Enabling the primary I2C bus for the IMU/compass multiplexer..."
# Append an explicit [all] section so this setting is not trapped under a model filter.
# Re-running setup replaces only our block; other boot settings remain intact.
sudo sed -i '/^# BEGIN AGIR I2C$/,/^# END AGIR I2C$/d' "$BOOT_CONFIG"
sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# BEGIN AGIR I2C
[all]
dtparam=i2c_arm=on
# END AGIR I2C
EOF
printf 'i2c-dev\n' | sudo tee /etc/modules-load.d/agir-i2c.conf >/dev/null
sudo modprobe i2c-dev

# Both ultrasonic sensors and GPS currently use USB adapters. No STM32 UART,
# fixed 115200 baud rate, Bluetooth disable or Pi 5 overlay is needed here.
# The node owns multiplexer channel switching; setup must not probe/select channels.

echo "🔌 Configuring universal permanent permissions (666) for Serial, USB, I2C..."

# We create a rules file using wildcards (*)
sudo tee /etc/udev/rules.d/99-sailing-hardware.rules > /dev/null <<EOF
# Permissions for the USB serial adapters used by ultrasonic sensors and GPS
KERNEL=="ttyACM[0-9]*", MODE="0666"
KERNEL=="ttyUSB[0-9]*", MODE="0666"

# Permissions for ALL I2C buses
KERNEL=="i2c-[0-9]*", MODE="0666"

# Permissions for ALL GPIO pins
KERNEL=="gpiochip[0-9]*", MODE="0666"
EOF

# Apply rules immediately
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ UDEV hardware rules successfully applied."

########################################
# 2) Docker + Compose
########################################

if ! command -v docker >/dev/null 2>&1; then
  echo "🐋 Docker not found, installing it..."
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sudo sh /tmp/get-docker.sh
else
  echo "🐋 Docker already installed: $(docker --version)"
fi
sudo systemctl enable --now docker

echo "Checking the Docker Compose plugin..."
if ! sudo docker compose version >/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-plugin
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin unavailable. Install the plugin before continuing."
  exit 1
fi
# Preserve the desktop user's HOME for the Compose Xauthority bind mount under sudo.
compose() { sudo env HOME="$USER_HOME" docker compose -f "$COMPOSE_FILE" "$@"; }

# docker group for current user
if ! id -nG "$USER" | grep -q '\bdocker\b'; then
  echo "👥 Adding $USER to docker group (full effect after new login)..."
  sudo usermod -aG docker "$USER" || true
fi

########################################
# 3) Clone/update Sailing_ROS repo (main branch)
########################################

mkdir -p "$BASE_DIR"

# fix permissions of the whole repo BEFORE touching git
if [ -d "$REPO_DIR" ]; then
  echo "🔑 Fixing permissions for existing repo (for git + ros)..."
  sudo chown -R "$USER":"$USER" "$REPO_DIR"
fi

if [ -d "$REPO_DIR/.git" ]; then
  echo "🔄 Existing repo in $REPO_DIR, aligning to origin/$BRANCH..."

  # --- Update the token even if the repo exists ---
  git -C "$REPO_DIR" remote set-url origin "https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git"

  git -C "$REPO_DIR" fetch --all --prune
  git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || true
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  echo "📥 Cloning repo into $REPO_DIR..."
  git clone -b "$BRANCH" "https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git" "$REPO_DIR"
fi

########################################
# 4) Workspace permissions fix + build cleanup
########################################

echo "🔑 Fixing ros2_ws permissions for host and container..."
if [ -d "$ROS_WS" ]; then
  sudo chown -R "$USER":"$USER" "$ROS_WS"
  sudo chmod -R 777 "$ROS_WS"

  echo "🧹 Cleaning previous build/install/log..."
  sudo rm -rf "$ROS_WS/build" "$ROS_WS/install" "$ROS_WS/log"
  mkdir -p "$ROS_WS/log"
  sudo chown -R "$USER":"$USER" "$ROS_WS"
  sudo chmod -R 777 "$ROS_WS"
else
  echo "⚠️  Warning: ROS_WS does not exist yet: $ROS_WS"
fi

########################################
# 5) Build & up ROS container
########################################

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ compose.yaml not found at: $COMPOSE_FILE"
  echo "   Check that raspi_container dir exists and file is named correctly."
  exit 1
fi

echo "🧱 Stopping any old container..."
compose down --remove-orphans

echo "⚙️  Building ROS container (directory: $CONTAINER_DIR)..."
cd "$CONTAINER_DIR"
compose build --no-cache

echo "🚀 Starting ROS container in background..."
# Keep ROS stopped after a failed build as well as after a successful setup.
trap 'compose stop || true' EXIT
compose up -d

########################################
# 6) colcon build inside container
########################################

echo "⏳ Waiting a few seconds for container to start..."
sleep 5

# Make script executable FROM THE HOST (Raspberry)
# So I don't have to do it inside the container where I might lack permissions.
if [ -f "$ROS_WS/scripts/build.sh" ]; then
    echo "🔧 Making build.sh executable (from host)..."
    chmod +x "$ROS_WS/scripts/build.sh"
else
    echo "⚠️ Warning: Cannot find $ROS_WS/scripts/build.sh"
fi

echo "🏗️  Executing build.sh inside container: $CONTAINER_NAME"
sudo docker exec "$CONTAINER_NAME" bash -lc \
  "set -eo pipefail && \
   source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./build.sh --clean"

# Record the image used by this successful workspace build (inside ignored build/).
sudo docker image inspect --format '{{.Id}}' "$IMAGE_NAME" \
  | sudo tee "$ROS_WS/build/.agir_image_id" >/dev/null

# Refresh an already-installed boot entry point, without installing/starting a service.
if [[ -f /usr/local/bin/agir_regatta_start.sh ]]; then
  sudo install -m 0755 "$REPO_DIR/DAY_BEFORE_REGATTA/agir_regatta_start.sh" /usr/local/bin/agir_regatta_start.sh
fi

########################################
# 7) Stop and Shutdown
########################################

echo "✅ Compilation successfully completed."
echo "🛑 Stopping setup container..."
compose stop
trap - EXIT

echo "🎉 SETUP FINISHED! The system is ready but STOPPED."
echo "👉 To start use the RUN script."
echo "Reboot before running sensors so the I2C boot configuration takes effect."
echo "USB port assignments in sensors/config/params.yaml still need hardware confirmation."
echo "Wi-Fi guardian and boot-service installation remain separate steps; see DAY_BEFORE_REGATTA/README.md."
