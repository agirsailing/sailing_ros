#!/usr/bin/env bash
# Loaded by lib/common.sh before Git changes the checkout.

workspace_clean() {
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
}

workspace_read_previous_image() {
  OLD_IMAGE_ID=""
  if [[ -f "$BUILD_IMAGE_FILE" ]]; then
    OLD_IMAGE_ID="$(cat "$BUILD_IMAGE_FILE")"
  fi
}

workspace_select_build_mode() {
  NEW_IMAGE_ID="$(sudo docker image inspect --format '{{.Id}}' "$IMAGE_NAME")"
  if [[ "$OLD_IMAGE_ID" != "$NEW_IMAGE_ID" ]]; then
    echo "Image changed or build provenance unknown: selecting a clean ROS build."
    BUILD_MODE="--clean"
  fi
}

workspace_exec() {
  sudo docker exec "$CONTAINER_NAME" bash -lc \
    "set -eo pipefail && \
     source /opt/ros/jazzy/setup.bash && \
     cd /home/ros/ros2_ws/scripts && \
     ./build.sh $1"
}

workspace_build_full() {
  # Make script executable FROM THE HOST (Raspberry)
  # So I don't have to do it inside the container where I might lack permissions.
  if [ -f "$ROS_WS/scripts/build.sh" ]; then
      echo "🔧 Making build.sh executable (from host)..."
      chmod +x "$ROS_WS/scripts/build.sh"
  else
      echo "⚠️ Warning: Cannot find $ROS_WS/scripts/build.sh"
  fi

  echo "🏗️  Executing build.sh inside container: $CONTAINER_NAME"
  workspace_exec --clean

  # Record the image used by this successful workspace build (inside ignored build/).
  sudo docker image inspect --format '{{.Id}}' "$IMAGE_NAME" \
    | sudo tee "$ROS_WS/build/.agir_image_id" >/dev/null
}

workspace_build_quick() {
  echo "3) Building the ROS workspace ($BUILD_MODE)..."
  # Make build.sh executable for safety
  chmod +x "$REPO_DIR/ros2_ws/scripts/build.sh" 2>/dev/null || true

  # Ordinary source updates retain build/install/log. Use --clean after removing or
  # renaming packages; image changes already select a clean build automatically.
  workspace_exec "$BUILD_MODE"

  printf '%s\n' "$NEW_IMAGE_ID" | sudo tee "$BUILD_IMAGE_FILE" >/dev/null
}
