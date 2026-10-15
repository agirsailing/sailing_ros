#!/usr/bin/env bash
# Loaded by lib/common.sh before Git changes the checkout.

docker_install() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "🐋 Docker not found, installing it..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
  else
    echo "🐋 Docker already installed: $(docker --version)"
  fi
  sudo systemctl enable --now docker

  echo "Checking the Docker Compose plugin..."
  if ! sudo docker compose version >/dev/null 2>&1; then
    sudo apt-get install -y docker-compose-plugin
  fi
  if ! sudo docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin unavailable. Install the plugin before continuing."
    exit 1
  fi

  # docker group for current user
  if ! id -nG "$USER" | grep -q '\bdocker\b'; then
    echo "👥 Adding $USER to docker group (full effect after new login)..."
    sudo usermod -aG docker "$USER" || true
  fi
}

docker_require_compose() {
  if ! sudo docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin missing: run the base setup first."
    exit 1
  fi
}

docker_rebuild() {
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ compose.yaml not found at: $COMPOSE_FILE"
    echo "   Check that raspi_container dir exists and file is named correctly."
    exit 1
  fi

  echo "🧱 Stopping any old container..."
  compose down --remove-orphans

  echo "⚙️  Building ROS container (directory: $CONTAINER_DIR)..."
  cd "$CONTAINER_DIR"
  compose build --no-cache
}
