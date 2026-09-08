#!/bin/bash
set -e # Se un comando fallisce, ferma tutto lo script

# ==========================================
# 1. SETUP PERCORSI ASSOLUTI
# ==========================================
# Ottiene la cartella dove si trova QUESTO script (es. /home/ros/ros2_ws/scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# La root del workspace è un livello sopra (es. /home/ros/ros2_ws)
WS_DIR="$(dirname "$SCRIPT_DIR")"

echo "📍 Workspace root detected: $WS_DIR"

# ==========================================
# 2. PULIZIA PROFONDA (The Cleaner)
# ==========================================
echo "🧹 Cleaning up EVERYTHING..."

# A. Cancella le cartelle di build ufficiali (nella root)
rm -rf "$WS_DIR/build" "$WS_DIR/install" "$WS_DIR/log"

# B. Cancella eventuali "incidenti" (cartelle build finite per sbaglio in src o scripts)
rm -rf "$WS_DIR/src/build" "$WS_DIR/src/install" "$WS_DIR/src/log"
rm -rf "$WS_DIR/scripts/build" "$WS_DIR/scripts/install" "$WS_DIR/scripts/log"

echo "✨ Workspace perfettamente pulito."

# ==========================================
# 3. GENERAZIONE CODICE
# ==========================================
echo "🔧 Generating ROS endpoints..."
# Assicurati che lo script python sia in 'scripts' (se è in tools, cambia il path qui sotto)
python3 "$WS_DIR/tools/gen_endpoints.py"

# ==========================================
# 4. COMPILAZIONE
# ==========================================
echo "🏗️  Building workspace..."

# Ci spostiamo nella root per lanciare colcon (FONDAMENTALE)
cd "$WS_DIR"

# A. Compila prima i messaggi (sail_msgs)
# È necessario per generare gli header che gli altri pacchetti useranno
colcon build --packages-select sail_msgs --symlink-install

# B. Carica l'ambiente dei messaggi appena creati
source install/setup.bash

# C. Compila tutto il resto
# Usiamo --base-paths src per essere sicuri che guardi solo in src
colcon build --symlink-install --base-paths src --event-handlers console_direct+ --parallel-workers 2

echo "✅ BUILD COMPLETATA CON SUCCESSO!"