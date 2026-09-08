#!/usr/bin/env bash
set -euo pipefail

echo "🚤 FAST UPDATE RASPBERRY SAILING TEAM — Incremental Pull & Build"

########################################
# ⚙️  PARAMETERS
########################################

USER_HOME="/home/agir"
BASE_DIR="$USER_HOME/2025_SOFTWARE"
REPO_DIR="$BASE_DIR/sailing_ros"
BRANCH="main"

CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="ros-boat"
COMPOSE_CMD="docker compose"

########################################

echo "⬇️ 1) Updating code from GitHub..."
if [ -d "$REPO_DIR/.git" ]; then
  echo "🔄 Downloading updates from main (keeping local files)..."
  
  # Use pull with rebase and autostash: 
  # Saves local modifications automatically, updates, and reapplies them on top of the new code.
  git -C "$REPO_DIR" pull origin "$BRANCH" --rebase --autostash

  echo "🔓 Relaxing permissions for the src folder for the Docker container..."
  sudo chmod -R 777 "$REPO_DIR/ros2_ws/src"

else
  echo "❌ Error: Repo not found in $REPO_DIR."
  echo "👉 You must run the BASE SETUP script first to initialize the system!"
  exit 1
fi

echo "🐳 2) Checking Docker Container status..."
# Check if the container is already running
if ! sudo docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}\$"; then
  echo "🚀 The container is not active. Starting it..."
  cd "$CONTAINER_DIR"
  sudo $COMPOSE_CMD -f "$COMPOSE_FILE" up -d
  echo "⏳ Waiting 3 seconds for ROS initialization..."
  sleep 3
else
  echo "✅ Container '$CONTAINER_NAME' already running. Entering directly."
fi

echo "🏗️ 3) Incremental build of ROS 2 workspace..."
# Make build.sh executable for safety
chmod +x "$REPO_DIR/ros2_ws/scripts/build.sh" 2>/dev/null || true

# Colcon will do a super fast incremental build because we haven't deleted the build/ and install/ folders
sudo docker exec "$CONTAINER_NAME" bash -lc \
  "set -eo pipefail && \
   source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./build.sh"

########################################
# 4) Shutdown (Optional)
########################################

# If your workflow expects the system to be stopped after the build waiting for the RUN script, leave it as is.
# If you want to test it immediately, you can comment out the line below.
echo "🛑 Stopping the container..."
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" stop

echo "🎉 UPDATE COMPLETED! Code updated and compiled in record time."
echo "👉 To start the system, use your RUN script."