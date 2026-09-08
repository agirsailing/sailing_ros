#!/bin/bash

echo "=========================================="
echo "⛵ Agir Sailing Team - ROS 2 PC Setup"
echo "=========================================="
echo "Costruisco e avvio il container di sviluppo..."

# Lancia docker compose direttamente, dato che siamo già nella cartella giusta
docker compose up -d --build

echo "=========================================="
echo "✅ Fatto! Il container 'ros-barca' è in esecuzione."
echo "Ora apri Docker Desktop e assicurati che sia verde."
echo "Vai su VS Code -> Ctrl+Shift+P -> 'Dev Containers: Attach to Running Container'."
echo "=========================================="