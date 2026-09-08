#!/usr/bin/env bash
set -euo pipefail

echo "🚤 FAST UPDATE RASPBERRY SAILING TEAM — Pull & Build Incrementale"

########################################
# ⚙️  PARAMETRI
########################################

USER_HOME="/home/barca"
BASE_DIR="$USER_HOME/2025_SOFTWARE"
REPO_DIR="$BASE_DIR/Sailing_ROS"
BRANCH="main"

CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="ros-barca"
COMPOSE_CMD="docker compose"

########################################

echo "⬇️ 1) Aggiornamento codice da GitHub..."
if [ -d "$REPO_DIR/.git" ]; then
  echo "🔄 Scarico gli aggiornamenti dal main (mantenendo i file locali)..."
  
  # Usa pull con rebase e autostash: 
  # Salva le modifiche locali in automatico, aggiorna, e le riapplica sopra al nuovo codice.
  git -C "$REPO_DIR" pull origin "$BRANCH" --rebase --autostash

  echo "🔓 Allento i permessi della cartella src per il container Docker..."
  sudo chmod -R 777 "$REPO_DIR/ros2_ws/src"

else
  echo "❌ Errore: Repo non trovata in $REPO_DIR."
  echo "👉 Devi prima eseguire lo script di SETUP BASE per inizializzare il sistema!"
  exit 1
fi

echo "🐳 2) Controllo stato Container Docker..."
# Controlla se il container è già in esecuzione
if ! sudo docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}\$"; then
  echo "🚀 Il container non è attivo. Lo avvio..."
  cd "$CONTAINER_DIR"
  sudo $COMPOSE_CMD -f "$COMPOSE_FILE" up -d
  echo "⏳ Aspetto 3 secondi per l'inizializzazione di ROS..."
  sleep 3
else
  echo "✅ Container '$CONTAINER_NAME' già in esecuzione. Entro direttamente."
fi

echo "🏗️ 3) Build incrementale del workspace ROS 2..."
# Rendiamo eseguibile il build.sh per sicurezza
chmod +x "$REPO_DIR/ros2_ws/scripts/build.sh" 2>/dev/null || true

# Colcon farà una build incrementale super veloce perché non abbiamo cancellato le cartelle build/ e install/
sudo docker exec "$CONTAINER_NAME" bash -lc \
  "set -eo pipefail && \
   source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./build.sh"

########################################
# 4) Chiusura (Opzionale)
########################################

# Se il tuo workflow prevede che dopo la build il sistema debba essere spento in attesa dello script di RUN, lascialo così.
# Se invece vuoi testarlo subito, puoi commentare la riga qui sotto.
echo "🛑 Spengo il container..."
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" stop

echo "🎉 UPDATE COMPLETATO! Codice aggiornato e compilato in tempo record."
echo "👉 Per avviare il sistema, usa il tuo script di RUN."