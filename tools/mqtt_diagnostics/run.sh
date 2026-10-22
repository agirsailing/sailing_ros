#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
ACTION="${1:-webapp}"
if [[ $# -gt 0 ]]; then shift; fi
PYTHON="${MQTT_TEST_PYTHON:-python3}"
if [[ -f .venv/bin/python ]]; then PYTHON="$SCRIPT_DIR/.venv/bin/python";
elif [[ -f .venv/Scripts/python.exe ]]; then PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"; fi

prepare_environment() {
  local base_python="${MQTT_TEST_PYTHON:-python3}"
  if [[ ! -f .venv/bin/python && ! -f .venv/Scripts/python.exe ]]; then
    # Raspberry Pi OS/Debian: install host prerequisites only when missing.
    if ! command -v "$base_python" >/dev/null 2>&1 || ! "$base_python" -c 'import venv, ensurepip' >/dev/null 2>&1; then
      if [[ "$(uname -s)" == Linux ]] && command -v apt-get >/dev/null 2>&1; then
        local -a privilege=()
        if [[ "$EUID" -ne 0 ]]; then privilege=(sudo); fi
        printf '%s\n' 'Installing Python prerequisites on this machine (sudo may ask for your password)...'
        "${privilege[@]}" apt-get update
        "${privilege[@]}" apt-get install -y python3 python3-venv
      else
        printf '%s\n' 'Install Python 3.10+ with venv, then rerun (or set MQTT_TEST_PYTHON).'
        return 1
      fi
    fi
    "$base_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required")'
    printf '%s\n' 'Creating the local Python environment...'
    "$base_python" -m venv .venv
  fi
  if [[ -f .venv/bin/python ]]; then PYTHON="$SCRIPT_DIR/.venv/bin/python";
  else PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"; fi
  if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    printf '%s\n' 'The local .venv is unusable or older than Python 3.10. Do not copy a Windows .venv to Linux.'
    return 1
  fi
  # Reuse installed versions; install again only if requirements are missing or changed.
  if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
from importlib.metadata import version
from pathlib import Path
for line in Path('requirements.txt').read_text().splitlines():
    if line.strip() and not line.lstrip().startswith('#'):
        name, required = line.strip().split('==')
        if version(name) != required:
            raise SystemExit(1)
import paho.mqtt.client
import yaml
PY
  then
    "$PYTHON" -m pip install -r requirements.txt
  fi
}

case "$ACTION" in
  setup)
    prepare_environment
    ;;
  local-up) docker compose up -d broker ;;
  local-down) docker compose down ;;
  local-logs) docker compose logs --no-color --timestamps broker ;;
  local)
    docker compose up -d broker
    "$PYTHON" probe.py --config local.json "$@"
    ;;
  cloud) "$PYTHON" probe.py --config config.local.json "$@" ;;
  webapp)
    ROS_CONFIG="$SCRIPT_DIR/../../ros2_ws/src/communication_web/config/mqtt_config.yaml"
    if [[ ! -f "$ROS_CONFIG" ]]; then
      printf '%s\n' 'Configure ros2_ws/src/communication_web/config/mqtt_config.yaml with broker and credentials first.'
      exit 1
    fi
    prepare_environment
    if [[ ! -f config.local.json ]]; then
      cp config.ros.example.json config.local.json
      printf '%s\n' 'Created config.local.json: reuses ROS credentials; WebSocket port 8084, path /mqtt.'
    fi
    printf '%s\n' 'Stop real boat publishers first. Open one webapp, without Demo.'
    "$PYTHON" probe.py --config config.local.json --ros-config "$ROS_CONFIG" \
      --duration 900 --dashboard-hz 5 --map-hz 2 --state-hz 0.5 \
      --ultrasonic-pattern ramp --webapp "$@"
    ;;
  analyze) "$PYTHON" probe.py --analyze "$@" ;;
  *)
    printf '%s\n' 'Usage: bash run.sh [webapp|setup|local|cloud|analyze|local-up|local-down|local-logs|help] [options]'
    printf '%s\n' 'Default: 15-minute webapp test, changing ultrasounds, dashboard 5 Hz, map 2 Hz, recording 0.5 Hz.'
    printf '%s\n' 'Example: bash run.sh webapp --dashboard-hz 2'
    printf '%s\n' 'Example: bash run.sh local --duration 900 --dashboard-hz 20 --map-hz 5 --state-hz 1'
    ;;
esac
