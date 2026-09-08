#!/usr/bin/env bash
set -e

WS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: bash run.sh [live] [ROS 2 launch arguments...]"
  echo "Starts the Agir sensors. Replay is not configured yet."
  exit 0
fi

# Keep the existing 'live' spelling while also allowing invocation without it.
if [[ "${1:-}" == "live" ]]; then
  shift
elif [[ $# -gt 0 && "$1" != -* && "$1" != *:=* ]]; then
  echo "Unknown mode: $1. Only 'live' is available."
  exit 1
fi

if [[ ! -f "$WS_DIR/install/setup.bash" ]]; then
  echo "Workspace is not built. Run: bash $WS_DIR/scripts/build.sh"
  exit 1
fi

echo "Starting Agir sensors from $WS_DIR"
source /opt/ros/jazzy/setup.bash
source "$WS_DIR/install/setup.bash"
exec ros2 launch sensors sensors_launch.py "$@"
