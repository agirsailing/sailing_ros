#!/bin/bash
set -euo pipefail

# ==============================================================================
# INSTALLER: Agir Wi-Fi Guardian
# ==============================================================================

SERVICE_NAME="agir_wifi_guardian.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SCRIPT_NAME="agir_wifi_check.sh"
SCRIPT_PATH="/usr/local/bin/$SCRIPT_NAME"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Run with sudo."
  exit 1
fi

echo "⛵ Installing $SERVICE_NAME..."

if [ ! -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
    echo "❌ Error: $SCRIPT_DIR/$SCRIPT_NAME not found!"
    exit 1
fi

if systemctl is-active --quiet "$SERVICE_NAME" || systemctl is-enabled --quiet "$SERVICE_NAME"; then
    systemctl stop "$SERVICE_NAME"
    systemctl disable "$SERVICE_NAME"
fi

cp "$SCRIPT_DIR/$SCRIPT_NAME" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=Agir - Wi-Fi Guardian (Check and Inject)
After=NetworkManager.service
Before=network-online.target
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=$SCRIPT_PATH
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo "🎉 Wi-Fi Guardian installation completed!"
