#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# CONFIGURATION PARAMETERS
# ==============================================================================
BASE_DIR="/home/agir/2025_SOFTWARE/sailing_ros"
COMPOSE_DIR="$BASE_DIR/Docker/raspi_container"
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
CONTAINER="ros-boat"
HOST_SCRIPT_PATH="$BASE_DIR/ros2_ws/scripts/run.sh"

# IP address to ping to ensure the network is up.
# Replace 8.8.8.8 with the local router's IP if there is no internet during the regatta!
TARGET_IP="8.8.8.8"

echo "🚀 Starting Sailing Team ROS System..."

# ------------------------------------------------------------------------------
# 0. WAITING FOR NETWORK CONNECTION
# ------------------------------------------------------------------------------
echo "⏳ Waiting for network connection to $TARGET_IP..."
# While ping fails, wait 2 seconds and retry indefinitely
while ! ping -c 1 -W 2 "$TARGET_IP" &> /dev/null; do
    echo "⚠️ Network not ready yet. Retrying in 2 seconds..."
    sleep 2
done
echo "✅ Network connected and working!"

# ------------------------------------------------------------------------------
# 1. PERMISSIONS AND DOCKER STARTUP (Without sudo!)
# ------------------------------------------------------------------------------
if [ -f "$HOST_SCRIPT_PATH" ]; then
    chmod +x "$HOST_SCRIPT_PATH"
fi

cd "$COMPOSE_DIR"
docker compose -f "$COMPOSE_FILE" up -d

echo "⏳ Waiting for container $CONTAINER..."
for i in {1..30}; do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "✅ Container active."
    break
  fi
  sleep 1
done

# ------------------------------------------------------------------------------
# 2. ROS EXECUTION (Without sudo!)
# ------------------------------------------------------------------------------
echo "🔥 Launching ROS 2 (run.sh live)..."

# We use -i instead of -it because systemd does not have a terminal (TTY)
docker exec -i "$CONTAINER" bash -lc \
  "source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./run.sh live"