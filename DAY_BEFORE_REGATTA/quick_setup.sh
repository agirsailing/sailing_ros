#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

main() {
  echo "AGIR UPDATE — cached Docker build and incremental ROS build"
  BUILD_MODE="--incremental"
  if [[ "$#" -gt 1 || ( "$#" -eq 1 && "$1" != "--clean" ) ]]; then
    echo "Usage: bash quick_setup.sh [--clean]"
    exit 1
  fi
  if [[ "$#" -eq 1 ]]; then BUILD_MODE="--clean"; fi
  require_user
  require_repo
  docker_require_compose
  runtime_stop_quick
  workspace_read_previous_image
  repository_step update

  echo "2) Updating the image using Docker's layer cache..."
  compose build
  workspace_select_build_mode
  trap 'compose stop || true' EXIT
  compose up -d
  workspace_build_quick
  runtime_refresh_entrypoint

  echo "🛑 Stopping the container..."
  compose stop
  trap - EXIT
  echo "UPDATE COMPLETED. ROS and the regatta service are stopped."
  echo "If installed, restart with: sudo systemctl start $REGATTA_SERVICE"
  echo "Otherwise run: bash $REPO_DIR/DAY_BEFORE_REGATTA/run.sh"
}
main "$@"
