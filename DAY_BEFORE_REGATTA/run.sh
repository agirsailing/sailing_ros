#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
COMPOSE_DIR="$CONTAINER_DIR"
HOST_SCRIPT_PATH="$ROS_WS/scripts/run.sh"

# Require Internet reachability before starting ROS, not only a local Wi-Fi link.
# Once ROS starts, its MQTT gateways handle reconnects without this startup gate.
TARGET_IP="${AGIR_TARGET_IP:-8.8.8.8}"

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
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin unavailable; run the Pi 4 setup first."
    exit 1
fi
echo "🔥 Launching ROS 2 (run.sh live)..."
# ROS is the container's main process. Ctrl+C/ExecStop reaches ROS through
# Docker's init process, allowing nodes and the recorder to close before exit.
# Foreground supervision also lets systemd detect a failed ROS launch.
docker compose -f "$COMPOSE_FILE" -f "$CONTAINER_DIR/compose.run.yaml" \
  up --no-build --force-recreate --abort-on-container-exit --exit-code-from jazzy
