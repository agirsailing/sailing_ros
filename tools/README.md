# Strumenti esterni al runtime ROS

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../README.md)

[mqtt_diagnostics](mqtt_diagnostics/README.md) simula dashboard, mappa e stato
registrazione e confronta ricezione MQTT TCP/WebSocket. Può girare sul PC o sul
Raspberry senza container ROS. Per un broker Mosquitto locale usa Docker.

Il generatore degli endpoint e l'esportatore delle rosbag in CSV sono nei
[tools del workspace](../ros2_ws/tools/README.md). Non copiare una `.venv`
Windows sul Raspberry e non committare configurazioni private o risultati voluminosi.
