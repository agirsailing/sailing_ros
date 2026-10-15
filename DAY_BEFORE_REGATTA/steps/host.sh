#!/usr/bin/env bash
# Loaded by lib/common.sh before Git changes the checkout.

host_check_board() {
  if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "This setup requires a 64-bit ARM operating system."
    exit 1
  fi
  MODEL="$(tr -d '\0' < /proc/device-tree/model)"
  if [[ "$MODEL" != *"Raspberry Pi 4"* ]]; then
    echo "This setup targets Raspberry Pi 4; detected: $MODEL"
    exit 1
  fi
  if [[ -f /boot/firmware/config.txt ]]; then
    BOOT_CONFIG=/boot/firmware/config.txt
  elif [[ -f /boot/config.txt ]]; then
    BOOT_CONFIG=/boot/config.txt
  else
    echo "Cannot find Raspberry Pi boot configuration."
    exit 1
  fi
}

host_configure() {
  HOSTN="$(hostnamectl --static || hostname)"
  if ! grep -q "^127\.0\.1\.1\s\+$HOSTN" /etc/hosts; then
    echo "🔧 Aligning /etc/hosts with hostname: $HOSTN"
    if grep -q "^127\.0\.1\.1" /etc/hosts; then
      sudo sed -i "s/^127\.0\.1\.1.*/127.0.1.1   $HOSTN/" /etc/hosts
    else
      echo "127.0.1.1   $HOSTN" | sudo tee -a /etc/hosts >/dev/null
    fi
  fi

  echo "🔄 Update & upgrade..."
  sudo apt-get update -y
  sudo apt-get upgrade -y

  echo "📦 Installing base packages (SSH, git, curl, nano, tree, ca-certificates, lsb-release)..."
  sudo apt-get install -y \
    openssh-client openssh-server \
    git curl nano tree ca-certificates lsb-release i2c-tools gpiod

  echo "📡 Enabling SSH server..."
  sudo systemctl enable ssh
  sudo systemctl start ssh
}
