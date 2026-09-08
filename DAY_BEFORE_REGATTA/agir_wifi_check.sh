#!/bin/bash
set -euo pipefail

# The over-the-air network name (SSID)
WIFI_SSID="" #example: orca-wifi
WIFI_PASS="" #example: blablabla

# The name under which Linux saved the profile (as seen by nmcli)
WIFI_PROFILE="" #example: netplan-wlan0-orca-wifi

echo "🔍 [WIFI GUARDIAN] Checking network presence: $WIFI_PROFILE"

if ! systemctl is-active --quiet NetworkManager; then
    echo "⚠️ NetworkManager not active. Exiting."
    exit 1
fi

if ! nmcli connection show | grep -q "$WIFI_PROFILE"; then
    echo "⚠️ Profile '$WIFI_PROFILE' not found! Injection in progress..."
    sudo nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS"
    echo "✅ Profile restored!"
else
    echo "✅ Profile exists. Forcing autoconnect for safety."
    # HERE'S THE MAGIC: We use the correct profile name for the modifications!
    sudo nmcli connection modify "$WIFI_PROFILE" connection.autoconnect yes
fi

exit 0