#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Define the whole workflow before updating the checkout containing this file.
main() {
  echo "AGIR RASPBERRY PI 4 SETUP — USB sensors, I2C, GPIO and ROS"
  require_user
  repository_validate_credentials
  host_check_board
  runtime_stop_full

  echo "🔎 Current user: $USER"
  echo "📁 BASE_DIR:   $BASE_DIR"
  echo "📁 REPO_DIR:   $REPO_DIR"
  echo "🌿 Branch:     $BRANCH"
  host_configure
  hardware_configure
  docker_install
  repository_step full
  workspace_clean
  docker_rebuild

  echo "🚀 Starting ROS container in background..."
  trap 'compose stop || true' EXIT
  compose up -d
  echo "⏳ Waiting a few seconds for container to start..."
  sleep 5
  workspace_build_full
  runtime_refresh_entrypoint

  echo "✅ Compilation successfully completed."
  echo "🛑 Stopping setup container..."
  compose stop
  trap - EXIT
  echo "🎉 SETUP FINISHED! The system is ready but STOPPED."
  echo "👉 To start use the RUN script."
  echo "Reboot before running sensors so the I2C boot configuration takes effect."
  echo "Keep USB sensors on their assigned ports: left=1.4, right=1.3, GPS=1.2, IMU=1.1."
  echo "Test manually with: bash $REPO_DIR/DAY_BEFORE_REGATTA/run.sh"
  echo "Only after manual testing, enable autostart yourself with: sudo bash $REPO_DIR/DAY_BEFORE_REGATTA/autostart_setup.sh"
}
main "$@"