#!/usr/bin/env bash
set -euo pipefail

echo "🚤 SETUP RASPBERRY SAILING TEAM — ROS container + workspace"

########################################
# ⚙️  PARAMETRI DA ADATTARE
########################################

USER_HOME="/home/barca"
BASE_DIR="$USER_HOME/2025_SOFTWARE"

GIT_USER=""
GIT_TOKEN=""   # 
REPO_SLUG="Sailing-Team-Polimi/Sailing_ROS"

REPO_DIR="$BASE_DIR/Sailing_ROS"
BRANCH="main"

ROS_WS="$REPO_DIR/ros2_ws"
CONTAINER_DIR="$REPO_DIR/Docker/raspi_container"
COMPOSE_FILE="$CONTAINER_DIR/compose.yaml"
CONTAINER_NAME="ros-barca"

########################################

echo "🔎 Utente corrente: $USER"
echo "📁 BASE_DIR:   $BASE_DIR"
echo "📁 REPO_DIR:   $REPO_DIR"
echo "🌿 Branch:     $BRANCH"

########################################
# 0) Fix hosts/hostname (optional ma utile)
########################################

HOSTN="$(hostnamectl --static || hostname)"
if ! grep -q "^127\.0\.1\.1\s\+$HOSTN" /etc/hosts; then
  echo "🔧 Allineo /etc/hosts con hostname: $HOSTN"
  if grep -q "^127\.0\.1\.1" /etc/hosts; then
    sudo sed -i "s/^127\.0\.1\.1.*/127.0.1.1   $HOSTN/" /etc/hosts
  else
    echo "127.0.1.1   $HOSTN" | sudo tee -a /etc/hosts >/dev/null
  fi
fi

########################################
# 1) Update & pacchetti base
########################################

echo "🔄 Update & upgrade..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "📦 Installo pacchetti base (SSH, git, curl, nano, ca-certificates, lsb-release)..."
sudo apt-get install -y \
  openssh-client openssh-server \
  git curl nano ca-certificates lsb-release

echo "📡 Abilito SSH server..."
sudo systemctl enable ssh
sudo systemctl start ssh

########################################
# 1.5) Configurazione Permessi Hardware (UDEV Rules & Boot config)
########################################

echo "🔌 Disattivo la console seriale di sistema per liberare le porte (ttyS0 / ttyAMA0)..."
# Disattiviamo e mascheriamo il demone che "ruba" i permessi alle porte seriali a runtime
sudo systemctl stop serial-getty@ttyS0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyS0.service 2>/dev/null || true
sudo systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyAMA0.service 2>/dev/null || true

echo "🔧 Disabilito la serial console al boot e abilito UART hardware..."
# Rimuove la console seriale dal file cmdline.txt per non sporcare il CAN bus all'avvio
if grep -q "console=serial0,115200" /boot/firmware/cmdline.txt; then
  sudo sed -i 's/console=serial0,115200 //g' /boot/firmware/cmdline.txt
fi

# Assicura che l'hardware UART sia acceso stabilmente in config.txt
if ! grep -q "^enable_uart=1" /boot/firmware/config.txt; then
  echo "enable_uart=1" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# NUOVO: Fix specifico per Raspberry Pi 5 (e 4/3) - Disabilita BT per liberare ttyAMA0 sui GPIO 14/15
echo "📻 Disabilito il Bluetooth per assegnare /dev/ttyAMA0 ai pin fisici..."
if ! grep -q "^dtoverlay=disable-bt" /boot/firmware/config.txt; then
  echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# QUESTA È LA PARTE CHE MANCAVA (Aggiunta del tuo amico)
echo "🔌 Forzo il routing di uart0 sui pin GPIO 14 e 15 (Specifico per Pi 5)..."
# Elimina il vecchio overlay generico se è rimasto da esecuzioni precedenti
sudo sed -i '/^dtoverlay=uart0$/d' /boot/firmware/config.txt

# Inserisce l'overlay corretto per l'architettura del Pi 5
if ! grep -q "^dtoverlay=uart0-pi5" /boot/firmware/config.txt; then
  echo "dtoverlay=uart0-pi5" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

echo "🛑 Disabilito i servizi di sistema Bluetooth..."
sudo systemctl stop hciuart.service 2>/dev/null || true
sudo systemctl mask hciuart.service 2>/dev/null || true
sudo systemctl stop bluetooth.service 2>/dev/null || true
sudo systemctl mask bluetooth.service 2>/dev/null || true

echo "🔌 Configuro i permessi permanenti universali (666) per Seriale, USB, I2C..."

# Creiamo un file con regole usando i caratteri jolly (*)
sudo tee /etc/udev/rules.d/99-sailing-hardware.rules > /dev/null <<EOF
# 1) Forzatura baud rate e permessi SOLO per le porte principali (ttyAMA0 e ttyS0 dedicate all'STM32)
KERNEL=="ttyAMA0", MODE="0666", RUN+="/bin/stty -F /dev/%k 115200 cs8 -cstopb -parenb raw -echo -ixon -ixoff -crtscts"
KERNEL=="ttyS0", MODE="0666", RUN+="/bin/stty -F /dev/%k 115200 cs8 -cstopb -parenb raw -echo -ixon -ixoff -crtscts"

# 2) SOLO permessi universali (NO forzatura baud rate) per tutte le altre porte (es. ttyAMA1 per il GPS, USB, ecc.)
KERNEL=="ttyAMA[1-9]*", MODE="0666"
KERNEL=="ttyS[1-9]*", MODE="0666"
KERNEL=="ttyACM[0-9]*", MODE="0666"
KERNEL=="ttyUSB[0-9]*", MODE="0666"
EOF

# Applichiamo le regole immediatamente
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ Regole hardware UDEV e configurazioni di boot applicate con successo."

########################################
# 2) Docker + Compose
########################################

if ! command -v docker >/dev/null 2>&1; then
  echo "🐋 Docker non trovato, lo installo..."
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sudo sh /tmp/get-docker.sh
  sudo systemctl enable docker
  sudo systemctl start docker
else
  echo "🐋 Docker già installato: $(docker --version)"
fi

echo "🧩 Installo docker-compose-plugin (Compose v2, se non c'è)..."
sudo apt-get install -y docker-compose-plugin || true

COMPOSE_CMD="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  echo "⚠️  docker compose (v2) non disponibile, provo con docker-compose (v1)..."
  sudo apt-get install -y docker-compose || true
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  else
    echo "❌ Nessun Docker Compose disponibile. Controlla APT/mirror."
    exit 1
  fi
fi
echo "✅ Userò: $COMPOSE_CMD"

# Gruppo docker per l'utente corrente
if ! id -nG "$USER" | grep -q '\bdocker\b'; then
  echo "👥 Aggiungo $USER al gruppo docker (effetto pieno dopo nuovo login)..."
  sudo usermod -aG docker "$USER" || true
fi

########################################
# 3) Clona/aggiorna la repo Sailing_ROS (branch main)
########################################

mkdir -p "$BASE_DIR"

# sistemazione permessi dell'intera repo PRIMA di toccare git
if [ -d "$REPO_DIR" ]; then
  echo "🔑 Sistemazione permessi repo esistente (per git + ros)..."
  sudo chown -R "$USER":"$USER" "$REPO_DIR"
fi

if [ -d "$REPO_DIR/.git" ]; then
  echo "🔄 Repo esistente in $REPO_DIR, allineo a origin/$BRANCH..."

  # --- Aggiorna il token anche se la repo esiste ---
  git -C "$REPO_DIR" remote set-url origin "https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git"

  git -C "$REPO_DIR" fetch --all --prune
  git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || true
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  echo "📥 Clono la repo in $REPO_DIR..."
  if [ "$GIT_TOKEN" = "INSERISCI_IL_TUO_TOKEN_QUI" ]; then
    echo "❌ Devi impostare il GIT_TOKEN nello script prima di eseguirlo."
    exit 1
  fi
  git clone -b "$BRANCH" "https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git" "$REPO_DIR"
fi

########################################
# 4) Sistemazione permessi workspace + pulizia build
########################################

echo "🔑 Sistemazione permessi ros2_ws per host e container..."
if [ -d "$ROS_WS" ]; then
  sudo chown -R "$USER":"$USER" "$ROS_WS"
  sudo chmod -R 777 "$ROS_WS"

  echo "🧹 Pulizia build/install/log precedenti..."
  sudo rm -rf "$ROS_WS/build" "$ROS_WS/install" "$ROS_WS/log"
  mkdir -p "$ROS_WS/log"
  sudo chown -R "$USER":"$USER" "$ROS_WS"
  sudo chmod -R 777 "$ROS_WS"
else
  echo "⚠️  Attenzione: ROS_WS non esiste ancora: $ROS_WS"
fi

########################################
# 5) Build & up del container ROS
########################################

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ compose.yaml non trovato in: $COMPOSE_FILE"
  echo "   Controlla che la dir raspi_container esista e che il file si chiami così."
  exit 1
fi

echo "🧱 Stop di un eventuale container vecchio..."
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" down --remove-orphans -v || true

echo "🧹 Rimuovo immagini docker inutilizzate (dangling + non usate)..."
sudo docker image prune -af || true

echo "⚙️  Build del container ROS (directory: $CONTAINER_DIR)..."
cd "$CONTAINER_DIR"
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" build --no-cache

echo "🚀 Avvio del container ROS in background..."
sudo $COMPOSE_CMD -f "$COMPOSE_FILE" up -d

########################################
# 6) colcon build dentro al container
########################################

echo "⏳ Aspetto qualche secondo che il container parta..."
sleep 5

# Rendo eseguibile lo script DALL'HOST (Raspberry)
# Così non devo farlo dentro il container dove potrei non avere i permessi.
if [ -f "$ROS_WS/scripts/build.sh" ]; then
    echo "🔧 Rendo eseguibile build.sh (dall'host)..."
    chmod +x "$ROS_WS/scripts/build.sh"
else
    echo "⚠️ Attenzione: Non trovo $ROS_WS/scripts/build.sh"
fi

echo "🏗️  Eseguo build.sh dentro al container: $CONTAINER_NAME"
sudo docker exec "$CONTAINER_NAME" bash -lc \
  "set -eo pipefail && \
   source /opt/ros/jazzy/setup.bash && \
   cd /home/ros/ros2_ws/scripts && \
   ./build.sh"

########################################
# 7) Stop e Chiusura
########################################

echo "✅ Compilazione completata con successo."
echo "🛑 Spengo il container di setup..."
sudo docker compose -f "$COMPOSE_FILE" stop

echo "🎉 SETUP FINITO! Il sistema è pronto ma SPENTO."
echo "⚠️  ATTENZIONE: È necessario riavviare il Raspberry per applicare i permessi Docker e abilitare l'hardware Seriale."
echo "👉 Esegui il comando: sudo reboot"
echo "👉 Per avviare (dopo il riavvio) usa lo script di RUN."