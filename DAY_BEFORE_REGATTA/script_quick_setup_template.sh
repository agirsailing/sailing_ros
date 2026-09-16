#!/usr/bin/env bash
set -euo pipefail

echo "AGIR UPDATE — cached Docker build and incremental ROS build"

########################################
# ⚙️  PARAMETERS
########################################

USER_HOME="/home/agir"
BASE_DIR="$USER_HOME/2025_SOFTWARE"
REPO_DIR="$BASE_DIR/sailing_ros"
BRANCH="main"

CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="agir-ros-raspi"
IMAGE_NAME="agirsailing:jazzy-raspi"
REGATTA_SERVICE="agir_regatta.service"
BUILD_IMAGE_FILE="$REPO_DIR/ros2_ws/build/.agir_image_id"
BUILD_MODE="--incremental"

if [[ "$#" -gt 1 || ( "$#" -eq 1 && "$1" != "--clean" ) ]]; then
  echo "Usage: bash script_quick_setup_template.sh [--clean]"
  exit 1
fi
if [[ "$#" -eq 1 ]]; then
  BUILD_MODE="--clean"
fi
if [[ "$EUID" -eq 0 || "$HOME" != "$USER_HOME" ]]; then
  echo "Run this script as the user whose home is $USER_HOME."
  exit 1
fi
if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "Repository missing: run the Raspberry Pi 4 base setup first."
  exit 1
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin missing: run the base setup first."
  exit 1
fi
compose() { sudo env HOME="$USER_HOME" docker compose -f "$COMPOSE_FILE" "$@"; }

# Stop the supervisor BEFORE the container, so Restart=always cannot race the build.
# Leave the service stopped on success/failure; its boot enablement is unchanged.
if systemctl cat "$REGATTA_SERVICE" >/dev/null 2>&1; then
  sudo systemctl stop "$REGATTA_SERVICE"
fi
compose stop
# Compare against the last successful workspace build, including after a failed update.
OLD_IMAGE_ID=""
if [[ -f "$BUILD_IMAGE_FILE" ]]; then
  OLD_IMAGE_ID="$(cat "$BUILD_IMAGE_FILE")"
fi

########################################

echo "⬇️ 1) Updating code from GitHub..."
if [ -d "$REPO_DIR/.git" ]; then
  echo "🔄 Downloading updates from main (keeping local files)..."
  
  # Use pull with rebase and autostash: 
  # Saves local modifications automatically, updates, and reapplies them on top of the new code.
  git -C "$REPO_DIR" pull origin "$BRANCH" --rebase --autostash

  echo "Making the workspace writable by the container user..."
  sudo chmod -R 777 "$REPO_DIR/ros2_ws"

else
  echo "❌ Error: Repo not found in $REPO_DIR."
  echo "👉 You must run the BASE SETUP script first to initialize the system!"
  exit 1
fi

echo "2) Updating the image using Docker's layer cache..."
# Always evaluate the Dockerfile: changed dependencies invalidate the relevant layers.
compose build
NEW_IMAGE_ID="$(sudo docker image inspect --format '{{.Id}}' "$IMAGE_NAME")"
if [[ "$OLD_IMAGE_ID" != "$NEW_IMAGE_ID" ]]; then
  echo "Image changed or build provenance unknown: selecting a clean ROS build."
  BUILD_MODE="--clean"
fi
trap 'compose stop || true' EXIT
# Compose recreates the container when its image or configuration changed.
compose up -d

echo "3) Building the ROS workspace ($BUILD_MODE)..."
# Make build.sh executable for safety
chmod +x "$REPO_DIR/ros2_ws/scripts/build.sh" 2>/dev/null || true

# Ordinary source updates retain build/install/log. Use --clean after removing or
# renaming packages; image changes already select a clean build automatically.
sudo docker exec "$CONTAINER_NAME" bash -lc \
  "set -eo pipefail && \
   source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./build.sh $BUILD_MODE"

printf '%s\n' "$NEW_IMAGE_ID" | sudo tee "$BUILD_IMAGE_FILE" >/dev/null

# The service runs an installed copy: refresh it when the boot service was installed.
if [[ -f /usr/local/bin/agir_regatta_start.sh ]]; then
  sudo install -m 0755 "$REPO_DIR/DAY_BEFORE_REGATTA/agir_regatta_start.sh" /usr/local/bin/agir_regatta_start.sh
fi

########################################
# 4) Leave the system stopped until explicitly started
########################################

echo "🛑 Stopping the container..."
compose stop
trap - EXIT

echo "UPDATE COMPLETED. ROS and the regatta service are stopped."
echo "If installed, restart with: sudo systemctl start $REGATTA_SERVICE"
echo "Otherwise run DAY_BEFORE_REGATTA/agir_regatta_start.sh."
