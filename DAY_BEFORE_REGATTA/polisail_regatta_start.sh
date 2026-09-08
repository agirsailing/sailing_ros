#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# PARAMETRI DI CONFIGURAZIONE
# ==============================================================================
BASE_DIR="/home/barca/2025_SOFTWARE/Sailing_ROS"
COMPOSE_DIR="$BASE_DIR/Docker/raspi_container"
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
CONTAINER="ros-barca"
HOST_SCRIPT_PATH="$BASE_DIR/ros2_ws/scripts/run.sh"

# Indirizzo IP da pingare per assicurarsi che la rete sia attiva.
# Sostituisci 8.8.8.8 con l'IP del router locale se non c'è internet in regata!
TARGET_IP="8.8.8.8"

echo "🚀 Avvio Sailing Team ROS System..."

# ------------------------------------------------------------------------------
# 0. ATTESA CONNESSIONE DI RETE
# ------------------------------------------------------------------------------
echo "⏳ Attendo connessione di rete verso $TARGET_IP..."
# Finché il ping fallisce, aspetta 2 secondi e riprova all'infinito
while ! ping -c 1 -W 2 "$TARGET_IP" &> /dev/null; do
    echo "⚠️ Rete non ancora pronta. Riprovo tra 2 secondi..."
    sleep 2
done
echo "✅ Rete connessa e funzionante!"

# ------------------------------------------------------------------------------
# 1. PERMESSI E AVVIO DOCKER (Senza sudo!)
# ------------------------------------------------------------------------------
if [ -f "$HOST_SCRIPT_PATH" ]; then
    chmod +x "$HOST_SCRIPT_PATH"
fi

cd "$COMPOSE_DIR"
docker compose -f "$COMPOSE_FILE" up -d

echo "⏳ Attendo container $CONTAINER..."
for i in {1..30}; do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "✅ Container attivo."
    break
  fi
  sleep 1
done

# ------------------------------------------------------------------------------
# 2. ESECUZIONE DI ROS (Senza sudo!)
# ------------------------------------------------------------------------------
echo "🔥 Lancio ROS 2 (run.sh live)..."

# Usiamo -i invece di -it perché systemd non ha un terminale (TTY)
docker exec -i "$CONTAINER" bash -lc \
  "source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./run.sh live"