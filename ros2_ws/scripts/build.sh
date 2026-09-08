#!/usr/bin/env bash
set -e # Stop immediately if a command fails.

# Resolve the workspace from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(dirname "$SCRIPT_DIR")"

echo "Workspace: $WS_DIR"
echo "Cleaning previous build artifacts..."
rm -rf "$WS_DIR/build" "$WS_DIR/install" "$WS_DIR/log"
rm -rf "$WS_DIR/src/build" "$WS_DIR/src/install" "$WS_DIR/src/log"
rm -rf "$WS_DIR/scripts/build" "$WS_DIR/scripts/install" "$WS_DIR/scripts/log"

source /opt/ros/jazzy/setup.bash
cd "$WS_DIR"

# Enable these only when the corresponding generator and package are added.
# python3 "$WS_DIR/tools/gen_endpoints.py"
# colcon build --packages-select sail_msgs --symlink-install
# source install/setup.bash

echo "Building workspace..."
colcon build --symlink-install --base-paths src --event-handlers console_direct+ --parallel-workers "${PARALLEL_WORKERS:-2}"
echo "Build completed successfully!"
