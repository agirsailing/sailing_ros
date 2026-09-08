#!/bin/bash
set -euo pipefail

# Il nome della rete "nell'aria" (SSID)
WIFI_SSID="orca-wifi"
WIFI_PASS="KalmanFilter"

# Il nome con cui Linux ha salvato il profilo (visto da nmcli)
WIFI_PROFILE="netplan-wlan0-orca-wifi"

echo "🔍 [WIFI GUARDIAN] Controllo presenza rete: $WIFI_PROFILE"

if ! systemctl is-active --quiet NetworkManager; then
    echo "⚠️ NetworkManager non attivo. Esco."
    exit 1
fi

if ! nmcli connection show | grep -q "$WIFI_PROFILE"; then
    echo "⚠️ Profilo '$WIFI_PROFILE' non trovato! Iniezione in corso..."
    sudo nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS"
    echo "✅ Profilo ripristinato!"
else
    echo "✅ Profilo esistente. Forzo l'autoconnect per sicurezza."
    # QUI STA LA MAGIA: Usiamo il nome profilo corretto per le modifiche!
    sudo nmcli connection modify "$WIFI_PROFILE" connection.autoconnect yes
fi

exit 0