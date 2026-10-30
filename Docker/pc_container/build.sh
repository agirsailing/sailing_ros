#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash build.sh [--gui]"
  echo "Default: build/start ROS development without an X server or host GPU."
  echo "--gui: enable X11 windows through a separately configured host X server."
  echo "       AGIR_DISPLAY defaults to host.docker.internal:0."
}

compose_files=(-f compose.yaml)
if [[ "$#" -gt 1 ]]; then
  usage >&2
  exit 2
fi
case "${1:-}" in
  '') ;;
  --gui) compose_files+=(-f compose.gui.yaml) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

# Resolve relative Compose paths from this script, regardless of the caller's cwd.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null 2>&1 || {
  echo "Docker was not found. Install/start Docker Desktop and reopen the terminal." >&2
  exit 1
}

echo "Building and starting the Agir development container..."
docker compose "${compose_files[@]}" up -d --build

echo "Done! The 'agir-ros-pc' container is ready."
echo "In VS Code: Dev Containers: Attach to Running Container."
if [[ "${1:-}" == --gui ]]; then
  echo "GUI display: ${AGIR_DISPLAY:-host.docker.internal:0} (host X server required)."
fi
