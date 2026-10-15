#!/bin/bash
set -euo pipefail

# The over-the-air network name (SSID)
WIFI_SSID="INSERT_WIFI_SSID"
WIFI_PASS="INSERT_WIFI_PASSWORD"

# The name under which Linux saved the profile (as seen by nmcli)
WIFI_PROFILE="INSERT_WIFI_PROFILE"

if [[ -z "$WIFI_SSID" || "$WIFI_SSID" == INSERT_* || -z "$WIFI_PASS" || "$WIFI_PASS" == INSERT_* || -z "$WIFI_PROFILE" || "$WIFI_PROFILE" == INSERT_* ]]; then
    echo "Fill the Wi-Fi placeholders before installing/running the guardian."
    exit 1
fi

echo "🔍 [WIFI GUARDIAN] Checking network presence: $WIFI_PROFILE"

if ! systemctl is-active --quiet NetworkManager; then
    echo "⚠️ NetworkManager not active. Exiting."
    exit 1
fi

if ! nmcli connection show "$WIFI_PROFILE" >/dev/null 2>&1; then
    echo "⚠️ Profile '$WIFI_PROFILE' not found! Injection in progress..."
    sudo nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS" name "$WIFI_PROFILE"
    echo "✅ Profile restored!"
else
    echo "✅ Profile exists. Forcing autoconnect for safety."
    # HERE'S THE MAGIC: We use the correct profile name for the modifications!
    sudo nmcli connection modify "$WIFI_PROFILE" connection.autoconnect yes
fi

exit 0
