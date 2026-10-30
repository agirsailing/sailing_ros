# Sistema di bordo Agir — ROS 2

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md)

Questa repository raccoglie il software ROS 2 del sistema di bordo del **KTH Agir Sailing Team**.

**Responsabile della manutenzione:** Ettore Cirillo — [ettore.cirillo.dev@gmail.com](mailto:ettore.cirillo.dev@gmail.com).

## Introduzione

Il sistema acquisisce i dati dei sensori, elabora l'orientamento e stima l'altezza della linea di galleggiamento della barca rispetto all'acqua. Gestisce inoltre la telemetria MQTT verso la webapp, il ping delle boe e la registrazione delle sessioni ROS in formato MCAP. La webapp si trova nella repository separata `agir_boat_monitoring`.

Il software gira sul Raspberry Pi 4 con ROS 2 Jazzy in Docker e si gestisce via SSH, senza schermo o sessione desktop. L'ambiente Docker permette anche di sviluppare e provare il codice sul PC. Questo README offre una panoramica e rimanda alle guide e ai pacchetti per i dettagli.

## Struttura della repository

| Cartella | Percorso | Scopo | README dettagliato |
|---|---|---|---|
| `DAY_BEFORE_REGATTA` | [`DAY_BEFORE_REGATTA/`](DAY_BEFORE_REGATTA/) | Configurazione, aggiornamento, avvio e autostart del Raspberry Pi. | [Italiano](DAY_BEFORE_REGATTA/README.md) |
| `Docker` | [`Docker/`](Docker/) | Ambienti containerizzati per PC e Raspberry Pi. | [Italiano](Docker/README.md) |
| `guides` | [`guides/`](guides/) | Procedure di installazione, utilizzo, verifica e manutenzione. | [Italiano](guides/README.md) |
| `ros2_ws` | [`ros2_ws/`](ros2_ws/) | Workspace ROS 2 con pacchetti e strumenti di build/test. | [Italiano](ros2_ws/README.md) |
| `tools` | [`tools/`](tools/) | Diagnostica MQTT indipendente dai sensori e dal runtime ROS. | [Italiano](tools/README.md) |

Per approfondire il contenuto di una cartella, apri il relativo README dettagliato.

## Primi passi

1. Parti dal [README delle guide](guides/README.md): raccoglie i prerequisiti, la configurazione del PC e le istruzioni per collegarti al Raspberry via SSH.
2. Consulta la [panoramica del workspace](ros2_ws/README.md), con il diagramma dei collegamenti tra pacchetti, poi apri il README del componente su cui lavorerai per i dettagli dei nodi e dei topic.
3. Per preparare la barca segui la [prima installazione del Raspberry](guides/italiano/settaggio_raspberry.md), quindi [avvio e prove manuali](guides/italiano/avvio_sistema_ros.md). Abilita l'autostart dopo queste prove.
4. Per compilare e verificare una modifica consulta gli [script del workspace](ros2_ws/scripts/README.md).
