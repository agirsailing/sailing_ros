#!/usr/bin/env bash
set -e

# =========================
# Config
# =========================
WS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_PKG="poli_sail"

LIVE_LAUNCH="live_poli_sail_system.launch.py"
REPLAY_LAUNCH="replay_poli_sail_system.launch.py"
BAG_FULL_TOPIC_LAUNCH="bag_full_topic.launch.py"

# =========================
# Helpers
# =========================
usage() {
  echo "Usage:"
  echo "  ./run.sh live    # run live system"
  echo "  ./run.sh replay  # run replay system"
  echo "  ./run.sh bag_full_topic  # run bag full topic system"
  exit 1
}

# =========================
# Args
# =========================
MODE="$1"

if [[ -z "$MODE" ]]; then
  echo "❌ Missing mode"
  usage
fi

case "$MODE" in
  live)
    LAUNCH_FILE="$LIVE_LAUNCH"
    ;;
  replay)
    LAUNCH_FILE="$REPLAY_LAUNCH"
    ;;
  bag_full_topic)
    LAUNCH_FILE="$BAG_FULL_TOPIC_LAUNCH"
    ;;
  *)
    echo "❌ Unknown mode: $MODE"
    usage
    ;;
esac

# =========================
# Environment
# =========================
echo "🚀 Starting PoliSail system in '$MODE' mode"
echo "📦 Workspace: $WS_DIR"
echo "📄 Launch file: $LAUNCH_FILE"

source /opt/ros/jazzy/setup.bash
source "$WS_DIR/install/setup.bash"

# =========================
# Run
# =========================
exec ros2 launch "$LAUNCH_PKG" "$LAUNCH_FILE"
