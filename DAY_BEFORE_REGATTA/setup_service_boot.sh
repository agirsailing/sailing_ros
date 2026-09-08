#!/bin/bash

# ==============================================================================
# SCRIPT DI INSTALLAZIONE: PoliSail Regatta Service (VERSIONE CORRETTA)
# ==============================================================================
# Questo script automatizza l'installazione, la configurazione e l'avvio
# del servizio systemd per far partire la barca in automatico al boot.
# ==============================================================================

SERVICE_NAME="polisail_regatta.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SCRIPT_NAME="polisail_regatta_start.sh"
SCRIPT_PATH="/usr/local/bin/$SCRIPT_NAME"

# Assicurati di eseguire lo script con sudo
if [ "$EUID" -ne 0 ]; then
  echo "❌ Errore: Questo script deve essere eseguito con i permessi di root (usa sudo)."
  exit 1
fi

echo "⛵ Inizio configurazione del servizio $SERVICE_NAME..."

# ------------------------------------------------------------------------------
# 1. CONTROLLO E RIMOZIONE DEL SERVIZIO ESISTENTE
# ------------------------------------------------------------------------------
if systemctl is-active --quiet "$SERVICE_NAME" || systemctl is-enabled --quiet "$SERVICE_NAME"; then
    echo "⚠️  Il servizio $SERVICE_NAME è già attivo o abilitato. Lo fermo e lo disabilito..."
    systemctl stop "$SERVICE_NAME"
    systemctl disable "$SERVICE_NAME"
    echo "✅ Vecchio servizio fermato."
fi

# Rimuovo i vecchi file se esistono
rm -f "$SERVICE_PATH"

if [ -f "$SCRIPT_PATH" ]; then
    rm "$SCRIPT_PATH"
fi

# ------------------------------------------------------------------------------
# 2. COPIA DEI NUOVI FILE (Assicurati che i file siano nella stessa cartella di questo script)
# ------------------------------------------------------------------------------
echo "📁 Copia dei file di sistema in corso..."

# Copio lo script di avvio
if [ ! -f "./$SCRIPT_NAME" ]; then
    echo "❌ Errore: File ./$SCRIPT_NAME non trovato nella cartella corrente!"
    exit 1
fi
cp "./$SCRIPT_NAME" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"
echo "✅ $SCRIPT_NAME copiato in $SCRIPT_PATH e reso eseguibile."

# Creo direttamente il file .service aggiornato con le modifiche concordate
echo "⚙️  Creazione del file $SERVICE_PATH con le impostazioni corrette (Wants invece di Requires)..."
cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=PoliSail - Regatta autostart (live)
After=docker.service network-online.target
Wants=docker.service

[Service]
Type=simple
User=barca
WorkingDirectory=/home/barca/2025_SOFTWARE/Sailing_ROS/DAY_BEFORE_REGATTA
ExecStart=/usr/local/bin/polisail_regatta_start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "✅ File .service creato."

# ------------------------------------------------------------------------------
# 3. ABILITAZIONE E AVVIO DEL SERVIZIO
# ------------------------------------------------------------------------------
echo "🔄 Ricarico i demoni di systemd..."
systemctl daemon-reload

echo "🚀 Abilito il servizio all'avvio..."
systemctl enable "$SERVICE_NAME"

echo "▶️  Avvio del servizio..."
systemctl start "$SERVICE_NAME"

# ------------------------------------------------------------------------------
# 4. CONTROLLO STATO FINALE
# ------------------------------------------------------------------------------
echo "------------------------------------------------------------------"
echo "🎉 Installazione completata! Controllo lo stato attuale:"
echo "------------------------------------------------------------------"
systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "📌 PROMEMORIA COMANDI UTILI:"
echo "Per vedere i log in diretta:  sudo journalctl -u $SERVICE_NAME -f"
echo "Per fermare il servizio:       sudo systemctl stop $SERVICE_NAME"
echo "Per disabilitarlo dopo regata: sudo systemctl disable --now $SERVICE_NAME"