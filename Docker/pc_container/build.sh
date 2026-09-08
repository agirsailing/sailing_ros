#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Agir Sailing Team - ROS 2 PC Setup"
echo "Building and starting the development container..."

# Resolve Compose relative to this script, regardless of the current directory.
docker compose -f "$SCRIPT_DIR/compose.yaml" up -d --build

echo "Done! The 'agir-ros-pc' container is running."
echo "In VS Code, open Ctrl+Shift+P -> Dev Containers: Attach to Running Container."
