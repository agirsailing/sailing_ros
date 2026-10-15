#!/usr/bin/env bash
set -euo pipefail

# Explicit opt-in: no other script calls this installer.
# Run only after verifying the complete system manually with run.sh.
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run this installer manually with sudo, after testing run.sh."
  exit 1
fi
require_repo
if [[ ! -f "$REPO_DIR/DAY_BEFORE_REGATTA/run.sh" || ! -f "$REPO_DIR/DAY_BEFORE_REGATTA/lib/common.sh" ]]; then
  echo "run.sh or its shared configuration is missing from the repository."
  exit 1
fi
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  echo "Configured service user does not exist: $DEPLOY_USER"
  exit 1
fi

SERVICE_PATH="/etc/systemd/system/$REGATTA_SERVICE"
echo "Installing $REGATTA_SERVICE for $DEPLOY_USER..."

# Stop the old supervisor and container before starting a single managed instance.
# Also stops a manual ROS run left inside the container after the terminal closed.
runtime_stop_full

# Generate from shared settings. The checked-in .service is a default reference.
# run.sh stays in the checkout alongside its configuration and modules.
cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Agir - Regatta autostart (live)
After=docker.service network-online.target
Wants=docker.service

[Service]
Type=simple
User=$DEPLOY_USER
Environment="HOME=$USER_HOME"
WorkingDirectory="$REPO_DIR/DAY_BEFORE_REGATTA"
ExecStart=/bin/bash "$REPO_DIR/DAY_BEFORE_REGATTA/run.sh"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$REGATTA_SERVICE"
systemctl start "$REGATTA_SERVICE"
systemctl status "$REGATTA_SERVICE" --no-pager

echo "Autostart enabled and ROS started."
echo "Logs: sudo journalctl -u $REGATTA_SERVICE -f"
echo "Disable autostart and stop the service: sudo systemctl disable --now $REGATTA_SERVICE"
