#!/usr/bin/env bash
set -e

# =========================
# Workspace and launch configuration
# =========================
WS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_PKG="orchestrator"
LIVE_LAUNCH="live_system.launch.py"
REPLAY_LAUNCH="replay_system.launch.py"
BAG_FULL_TOPIC_LAUNCH=""

# =========================
# Help
# =========================
usage() {
  echo "Usage: bash run.sh <mode> [ROS 2 launch arguments...]"
  echo "  live            Run the live system launch"
  echo "  replay          Run the replay system launch"
  if [[ -n "$BAG_FULL_TOPIC_LAUNCH" ]]; then
    echo "  bag_full_topic  Run the full-topic recording launch"
  fi
  exit "${1:-0}"
}

# =========================
# Select the launch mode
# =========================
MODE="${1:-}"
case "$MODE" in
  -h|--help)
    usage 0
    ;;
  live)
    LAUNCH_FILE="$LIVE_LAUNCH"
    ;;
  replay)
    LAUNCH_FILE="$REPLAY_LAUNCH"
    ;;
  bag_full_topic)
    if [[ -z "$BAG_FULL_TOPIC_LAUNCH" ]]; then
      echo "Mode 'bag_full_topic' is not configured for $LAUNCH_PKG."
      usage 1
    fi
    LAUNCH_FILE="$BAG_FULL_TOPIC_LAUNCH"
    ;;
  "")
    echo "Missing mode."
    usage 1
    ;;
  *)
    echo "Unknown mode: $MODE"
    usage 1
    ;;
esac
shift

# =========================
# Load the environment
# =========================
if [[ ! -f "$WS_DIR/install/setup.bash" ]]; then
  echo "Workspace is not built. Run: bash $WS_DIR/scripts/build.sh"
  exit 1
fi

echo "Starting $LAUNCH_PKG in '$MODE' mode"
echo "Workspace: $WS_DIR"
echo "Launch file: $LAUNCH_FILE"

source /opt/ros/jazzy/setup.bash
source "$WS_DIR/install/setup.bash"

# =========================
# Run and forward launch arguments
# =========================
exec ros2 launch "$LAUNCH_PKG" "$LAUNCH_FILE" "$@"
