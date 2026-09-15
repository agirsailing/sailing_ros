#!/usr/bin/env bash
set -e # Stop immediately if a command fails.

# =========================
# Workspace and configuration
# =========================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(dirname "$SCRIPT_DIR")"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-2}"

echo "Workspace: $WS_DIR"

# Check required inputs before removing previous build artifacts.
if [[ ! -f "$WS_DIR/tools/gen_endpoints.py" ]]; then
  echo "Endpoint generator not found: $WS_DIR/tools/gen_endpoints.py"
  exit 1
fi
if [[ ! -f "$WS_DIR/src/sail_msgs/package.xml" ]]; then
  echo "Interface package not found: $WS_DIR/src/sail_msgs"
  exit 1
fi

# =========================
# Clean previous build artifacts
# =========================
echo "Cleaning previous build artifacts..."
rm -rf "$WS_DIR/build" "$WS_DIR/install" "$WS_DIR/log"
rm -rf "$WS_DIR/src/build" "$WS_DIR/src/install" "$WS_DIR/src/log"
rm -rf "$WS_DIR/scripts/build" "$WS_DIR/scripts/install" "$WS_DIR/scripts/log"

# =========================
# Load ROS and generate endpoints
# =========================
source /opt/ros/jazzy/setup.bash
cd "$WS_DIR"

echo "Generating ROS endpoints..."
python3 "$WS_DIR/tools/gen_endpoints.py"

# =========================
# Build and load custom interfaces
# =========================
echo "Building sail_msgs..."
colcon build --symlink-install --base-paths src --packages-select sail_msgs --parallel-workers "$PARALLEL_WORKERS"
source "$WS_DIR/install/setup.bash"

# =========================
# Build the complete workspace
# =========================
echo "Building workspace..."
colcon build --symlink-install --base-paths src --event-handlers console_direct+ --parallel-workers "$PARALLEL_WORKERS"
echo "Build completed successfully!"
