#!/usr/bin/env bash
# Source-only configuration and functions. No deployment commands run on load.
AGIR_SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$AGIR_SETUP_DIR/config.local.sh" ]]; then
  source "$AGIR_SETUP_DIR/config.local.sh"
fi

USER_HOME="${AGIR_USER_HOME:-/home/boat}"
DEPLOY_USER="${AGIR_USER:-$(basename "$USER_HOME")}"
REPO_DIR="${AGIR_REPO_DIR:-$USER_HOME/2025_SOFTWARE/sailing_ros}"
BASE_DIR="$(dirname "$REPO_DIR")"
BRANCH="${AGIR_BRANCH:-main}"
GIT_USER="${AGIR_GIT_USER:-${GIT_USER:-}}"
GIT_TOKEN="${AGIR_GIT_TOKEN:-${GIT_TOKEN:-}}"
REPO_SLUG="agirsailing/sailing_ros"
ROS_WS="$REPO_DIR/ros2_ws"
CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="agir-ros-raspi"
IMAGE_NAME="agirsailing:jazzy-raspi"
REGATTA_SERVICE="agir_regatta.service"
BUILD_IMAGE_FILE="$ROS_WS/build/.agir_image_id"

require_user() {
  if [[ "$EUID" -eq 0 || "$HOME" != "$USER_HOME" ]]; then
    echo "Run this script as the user whose home is $USER_HOME."
    exit 1
  fi
}
require_repo() {
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "Repository missing: run the Raspberry Pi 4 base setup first."
    exit 1
  fi
}
# Keep the deployment user's HOME when invoking Compose through sudo.
# The Raspberry Compose has no desktop/session-dependent mounts.
compose() { sudo env HOME="$USER_HOME" docker compose -f "$COMPOSE_FILE" "$@"; }

# Pass resolved settings to the standalone Git step, including non-exported
# config.local.sh values when the setup scripts live outside the checkout.
repository_step() {
  AGIR_USER_HOME="$USER_HOME" AGIR_USER="$DEPLOY_USER" \
  AGIR_REPO_DIR="$REPO_DIR" AGIR_BRANCH="$BRANCH" \
  AGIR_GIT_USER="$GIT_USER" AGIR_GIT_TOKEN="$GIT_TOKEN" \
    bash "$AGIR_SETUP_DIR/steps/repository.sh" "$@"
}

# Load every function before fetch/reset/rebase can replace files on disk.
# Keeping steps in this shell also preserves state and EXIT traps across steps.
for agir_step in host hardware docker repository workspace runtime; do
  source "$AGIR_SETUP_DIR/steps/$agir_step.sh"
done
unset agir_step
