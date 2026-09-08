#!/usr/bin/env bash
set -euo pipefail

echo "🚤 SETUP RASPBERRY SAILING TEAM — ROS container + workspace"

########################################
# ⚙️  PARAMETERS TO ADAPT
########################################

USER_HOME="/home/agir"
BASE_DIR="$USER_HOME/2025_SOFTWARE"

GIT_USER=""
GIT_TOKEN="" 
REPO_SLUG="agirsailing/sailing_ros"

REPO_DIR="$BASE_DIR/sailing_ros"
BRANCH="main"

ROS_WS="$REPO_DIR/ros2_ws"
CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="ros-boat"

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
  git curl nano tree ca-certificates lsb-release

echo "📡 Enabling SSH server..."
sudo systemctl enable ssh
sudo systemctl start ssh

########################################
# 1.5) Hardware Permissions Configuration (UDEV Rules)
########################################

echo "🔌 Disabling system serial console to free up ports (ttyS0 / ttyAMA0)..."
# We disable and mask the daemon that "steals" permissions from serial ports
sudo systemctl stop serial-getty@ttyS0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyS0.service 2>/dev/null || true
sudo systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyAMA0.service 2>/dev/null || true

echo "🔌 Configuring universal permanent permissions (666) for Serial, USB, I2C..."

# We create a rules file using wildcards (*)
sudo tee /etc/udev/rules.d/99-sailing-hardware.rules > /dev/null <<EOF
# Permissions for ALL hardware serial ports and USB adapters
KERNEL=="ttyS[0-9]*", MODE="0666"
KERNEL=="ttyAMA[0-9]*", MODE="0666"
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
  sudo systemctl enable docker
  sudo systemctl start docker
else
  echo "🐋 Docker already installed: $(docker --version)"
fi

echo "🧩 Installing docker-compose-plugin (Compose v2, if missing)..."
sudo apt-get install -y docker-compose-plugin || true

COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  echo "⚠️  docker compose (v2) not available, trying with docker-compose (v1)..."
  sudo apt-get install -y docker-compose || true
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  else
    echo "❌ No Docker Compose available. Check APT/mirror."
    exit 1
  fi
fi
echo "✅ Will use: $COMPOSE_CMD"

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
  if [ "$GIT_TOKEN" = "INSERT_YOUR_TOKEN_HERE" ]; then
    echo "❌ You must set the GIT_TOKEN in the script before running it."
    exit 1
  fi
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
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" down --remove-orphans -v || true

echo "🧹 Removing unused docker images (dangling + unused)..."
sudo docker image prune -af || true

echo "⚙️  Building ROS container (directory: $CONTAINER_DIR)..."
cd "$CONTAINER_DIR"
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" build --no-cache

echo "🚀 Starting ROS container in background..."
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" up -d

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
   ./build.sh"

########################################
# 7) Stop and Shutdown
########################################

echo "✅ Compilation successfully completed."
echo "🛑 Stopping setup container..."
sudo docker compose -f "$COMPOSE_FILE" stop

echo "🎉 SETUP FINISHED! The system is ready but STOPPED."
echo "👉 To start use the RUN script."