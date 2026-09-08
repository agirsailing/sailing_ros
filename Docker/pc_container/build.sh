#!/bin/bash

echo "=========================================="
echo "⛵ Agir Sailing Team - ROS 2 PC Setup"
echo "=========================================="
echo "Building and starting the development container..."

docker compose up -d --build

echo "=========================================="
echo "✅ "Done! The 'agir-ros-pc' container is running."
echo "Ora apri Docker Desktop e assicurati che sia verde."
echo "In VS Code, open Ctrl+Shift+P -> Dev Containers: Attach to Running Container."
echo "=========================================="