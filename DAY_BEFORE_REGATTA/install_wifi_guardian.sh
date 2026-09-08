#!/bin/bash

# ==============================================================================
# INSTALLATORE: PoliSail Wi-Fi Guardian
# ==============================================================================

SERVICE_NAME="polisail_wifi_guardian.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SCRIPT_NAME="polisail_wifi_check.sh"
SCRIPT_PATH="/usr/local/bin/$SCRIPT_NAME"

if [ "$EUID" -ne 0 ]; then
  echo "❌ Errore: Esegui con sudo."
  exit 1
fi

echo "⛵ Installazione $SERVICE_NAME..."

if systemctl is-active --quiet "$SERVICE_NAME" || systemctl is-enabled --quiet "$SERVICE_NAME"; then
    systemctl stop "$SERVICE_NAME"
    systemctl disable "$SERVICE_NAME"
fi

if [ ! -f "./$SCRIPT_NAME" ]; then
    echo "❌ Errore: ./$SCRIPT_NAME non trovato qui!"
    exit 1
fi

cp "./$SCRIPT_NAME" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=PoliSail - Wi-Fi Guardian (Check and Inject)
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

echo "🎉 Installazione Wi-Fi Guardian completata!"