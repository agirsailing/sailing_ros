#!/usr/bin/env bash
set -euo pipefail

echo "⚙️ Setup UART (PL011 -> /dev/ttyAMA0) per Raspberry Pi 5..."

# 1. Disattiva la console seriale dal boot per liberare la porta
echo "🔌 Disattivo la serial console di Linux..."
if grep -q "console=serial0,115200" /boot/firmware/cmdline.txt; then
  sudo sed -i 's/console=serial0,115200 //g' /boot/firmware/cmdline.txt
fi

# 2. Configura config.txt per Raspberry Pi 5
echo "🔧 Abilito UART hardware e imposto l'overlay specifico per Pi 5..."
if ! grep -q "^enable_uart=1" /boot/firmware/config.txt; then
  echo "enable_uart=1" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

if ! grep -q "^dtoverlay=disable-bt" /boot/firmware/config.txt; then
  echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# Rimuovo l'eventuale "uart0" generico se era rimasto da vecchi script
sudo sed -i '/^dtoverlay=uart0$/d' /boot/firmware/config.txt

# Aggiungo la versione specifica per Pi 5
if ! grep -q "^dtoverlay=uart0-pi5" /boot/firmware/config.txt; then
  echo "dtoverlay=uart0-pi5" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# 3. Disabilita i servizi di sistema che "rubano" la seriale
echo "🛑 Spegnimento e mascheramento di serial-getty e Bluetooth..."
sudo systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyAMA0.service 2>/dev/null || true
sudo systemctl stop hciuart.service 2>/dev/null || true
sudo systemctl mask hciuart.service 2>/dev/null || true
sudo systemctl stop bluetooth.service 2>/dev/null || true
sudo systemctl mask bluetooth.service 2>/dev/null || true

# 4. Regola UDEV per forzare permessi e parametri STTY
echo "📝 Configuro i permessi (666) e la modalità RAW per /dev/ttyAMA0..."
sudo tee /etc/udev/rules.d/99-uart-hardware.rules > /dev/null <<EOF
KERNEL=="ttyAMA0", MODE="0666", RUN+="/bin/stty -F /dev/%k 115200 cs8 -cstopb -parenb raw -echo -ixon -ixoff -crtscts"
EOF

# Ricarica le regole udev
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ Setup completato!"
echo "⚠️ Riavvia il Raspberry Pi con 'sudo reboot' per applicare tutte le modifiche hardware."