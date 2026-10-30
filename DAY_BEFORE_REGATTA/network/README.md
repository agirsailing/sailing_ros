# Controllo opzionale del profilo Wi-Fi

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../../README.md)

[agir_wifi_check.sh](agir_wifi_check.sh) usa NetworkManager: se manca il profilo
lo crea con SSID/password configurati, altrimenti abilita autoconnect. È un
controllo **oneshot al boot**, non un monitor che ripristina ogni disconnessione.
Non verifica broker, latenza o accesso a Internet.

Compilare `WIFI_SSID`, `WIFI_PASS`, `WIFI_PROFILE` in una copia privata dello script;
tenere accanto [install_wifi_guardian.sh](install_wifi_guardian.sh). L'installer
copia lo script in `/usr/local/bin` e abilita/avvia subito il servizio:

```bash
sudo bash install_wifi_guardian.sh
systemctl status agir_wifi_guardian.service
journalctl -u agir_wifi_guardian.service -b
```

Non è richiamato da complete/quick. Non committare password: i placeholder nel
file tracciato devono rimanere tali. Per disattivarlo:
`sudo systemctl disable --now agir_wifi_guardian.service`.
Un profilo esistente con credenziali errate non viene riscritto dal controllo.
