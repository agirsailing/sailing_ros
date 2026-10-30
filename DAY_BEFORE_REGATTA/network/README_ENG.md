# Optional Wi-Fi profile check

_Updated on: 30/10/2026_

[Italiano](README.md) · [Repository index](../../README_ENG.md)

[agir_wifi_check.sh](agir_wifi_check.sh) uses NetworkManager: it creates a missing
profile with configured SSID/password, or enables autoconnect on an existing
profile. This is a **boot oneshot**, not a continuous disconnection recovery
monitor. It does not check the broker, latency or Internet connectivity.

Fill `WIFI_SSID`, `WIFI_PASS`, `WIFI_PROFILE` in a private script copy; keep
[install_wifi_guardian.sh](install_wifi_guardian.sh) alongside it. The installer
copies the script to `/usr/local/bin` and immediately enables/starts the service:

```bash
sudo bash install_wifi_guardian.sh
systemctl status agir_wifi_guardian.service
journalctl -u agir_wifi_guardian.service -b
```

Complete/quick do not call it. Never commit passwords: tracked placeholders must
remain placeholders. Disable with:
`sudo systemctl disable --now agir_wifi_guardian.service`.
The check does not rewrite an existing profile with incorrect credentials.
