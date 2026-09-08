#!/bin/bash

# ==============================================================================
# INSTALLATION SCRIPT: Agir Regatta Service (CORRECTED VERSION)
# ==============================================================================
# This script automates the installation, configuration, and startup
# of the systemd service to start the boat automatically at boot.
# ==============================================================================

SERVICE_NAME="agir_regatta.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SCRIPT_NAME="agir_regatta_start.sh"
SCRIPT_PATH="/usr/local/bin/$SCRIPT_NAME"

# Ensure you run the script with sudo
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: This script must be run with root privileges (use sudo)."
  exit 1
fi

echo "⛵ Starting configuration of the $SERVICE_NAME service..."

# ------------------------------------------------------------------------------
# 1. CHECK AND REMOVAL OF EXISTING SERVICE
# ------------------------------------------------------------------------------
if systemctl is-active --quiet "$SERVICE_NAME" || systemctl is-enabled --quiet "$SERVICE_NAME"; then
    echo "⚠️  The $SERVICE_NAME service is already active or enabled. Stopping and disabling it..."
    systemctl stop "$SERVICE_NAME"
    systemctl disable "$SERVICE_NAME"
    echo "✅ Old service stopped."
fi

# Remove old files if they exist
rm -f "$SERVICE_PATH"

if [ -f "$SCRIPT_PATH" ]; then
    rm "$SCRIPT_PATH"
fi

# ------------------------------------------------------------------------------
# 2. COPYING NEW FILES (Ensure files are in the same folder as this script)
# ------------------------------------------------------------------------------
echo "📁 Copying system files in progress..."

# Copying the startup script
if [ ! -f "./$SCRIPT_NAME" ]; then
    echo "❌ Error: File ./$SCRIPT_NAME not found in the current folder!"
    exit 1
fi
cp "./$SCRIPT_NAME" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"
echo "✅ $SCRIPT_NAME copied to $SCRIPT_PATH and made executable."

# Directly create the updated .service file with the agreed modifications
echo "⚙️  Creating the $SERVICE_PATH file with the correct settings (Wants instead of Requires)..."
cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=Agir - Regatta autostart (live)
After=docker.service network-online.target
Wants=docker.service

[Service]
Type=simple
User=agir
WorkingDirectory=/home/agir/2025_SOFTWARE/sailing_ros/DAY_BEFORE_REGATTA
ExecStart=/usr/local/bin/agir_regatta_start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "✅ .service file created."

# ------------------------------------------------------------------------------
# 3. ENABLING AND STARTING THE SERVICE
# ------------------------------------------------------------------------------
echo "🔄 Reloading systemd daemons..."
systemctl daemon-reload

echo "🚀 Enabling service at boot..."
systemctl enable "$SERVICE_NAME"

echo "▶️  Starting the service..."
systemctl start "$SERVICE_NAME"

# ------------------------------------------------------------------------------
# 4. FINAL STATUS CHECK
# ------------------------------------------------------------------------------
echo "------------------------------------------------------------------"
echo "🎉 Installation completed! Checking current status:"
echo "------------------------------------------------------------------"
systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "📌 USEFUL COMMANDS REMINDER:"
echo "To see live logs:       sudo journalctl -u $SERVICE_NAME -f"
echo "To stop the service:    sudo systemctl stop $SERVICE_NAME"
echo "To disable after race:  sudo systemctl disable --now $SERVICE_NAME"