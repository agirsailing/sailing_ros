# Ambiente Docker

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../README.md)

Questa cartella contiene ciò che serve per preparare gli ambienti ROS 2 Jazzy del progetto: uno per sviluppare sul PC e uno per eseguire il sistema sulla barca. I sorgenti dei nodi rimangono nel [workspace ros2_ws](../ros2_ws/README.md); qui definiamo l'ambiente in cui vengono compilati ed eseguiti.

## Perché usiamo Docker

Nel team sviluppiamo sul PC e poi trasferiamo il codice sul Raspberry tramite Git. Il programma, però, non dipende soltanto dai file che scriviamo: servono anche ROS, il compilatore, i pacchetti dei messaggi e le librerie per sensori e MQTT. Installare tutto a mano su ogni computer rende più difficile capire se un problema dipende dal codice o da un ambiente configurato diversamente.

Docker ci permette di descrivere queste installazioni nei file della repository. Chi entra nel team può costruire l'ambiente a partire da quelle istruzioni, senza installare ROS direttamente su Windows o macOS. Anche sul Raspberry le dipendenze dell'applicazione vengono installate nel container; il sistema operativo del Raspberry continua a gestire rete, dispositivi e servizi di avvio.

PC e Raspberry hanno due configurazioni distinte perché svolgono lavori diversi. Sul PC servono strumenti di sviluppo, analisi e, quando necessario, finestre grafiche. Sulla barca servono soprattutto l'accesso ai sensori e l'esecuzione senza schermo. Usiamo la stessa distribuzione ROS e manteniamo le dipendenze necessarie in entrambi gli ambienti, ma compiliamo il codice su ciascuna macchina: i risultati della compilazione del PC non vanno copiati sul Raspberry.

## Immagine, container e file condivisi

L'**immagine** è l'ambiente preparato da Docker: contiene ROS e le dipendenze installate seguendo il `Dockerfile`. Il **container** è l'ambiente in esecuzione ricavato da quell'immagine. Quando VS Code si collega al container, il suo terminale esegue i comandi al suo interno, anche se la finestra di VS Code è sul PC Windows o macOS.

I file del progetto vengono condivisi con il container tramite i **montaggi**, indicati in `compose.yaml`. Per esempio, modificando un nodo in `ros2_ws/src` dal PC, la modifica è subito visibile nella cartella corrispondente del container. Non occorre ricostruire l'immagine Docker a ogni modifica del codice: occorre invece ricompilare il workspace ROS quando richiesto.

## Struttura della cartella

```text
Docker/
├── pc_container/
│   ├── .dockerignore
│   ├── build.sh
│   ├── compose.gui.yaml
│   ├── compose.yaml
│   ├── Dockerfile
│   └── entrypoint.sh
├── raspi_container/
│   ├── .dockerignore
│   ├── compose.yaml
│   ├── Dockerfile
│   └── entrypoint.sh
├── README.md
└── README_ENG.md
```

I file hanno ruoli diversi e si usano insieme:

| File | A cosa serve |
|---|---|
| `Dockerfile` | Definisce l'immagine di partenza, installa le dipendenze e prepara l'utente e le cartelle del container. |
| `compose.yaml` | Definisce come avviare il container: nome, immagine, file condivisi, rete e, sul Raspberry, accesso ai dispositivi. |
| `entrypoint.sh` | All'avvio del container carica ROS e il workspace, poi esegue il comando ricevuto. |
| `build.sh` | Sul PC riunisce in un solo comando la costruzione dell'immagine e l'avvio del container. |
| `compose.gui.yaml` | Aggiunge la configurazione grafica del PC quando si usa `build.sh --gui`. |
| `.dockerignore` | Esclude file non necessari dall'insieme inviato a Docker durante la costruzione dell'immagine. |

## I due ambienti

| Caratteristica | PC | Raspberry Pi |
|---|---|---|
| Cartella | [pc_container](pc_container/) | [raspi_container](raspi_container/) |
| Utilizzo | Sviluppare, compilare, fare test e analizzare registrazioni. | Leggere i sensori ed eseguire il sistema di bordo. |
| Immagine di partenza | `osrf/ros:jazzy-desktop-full` | `ros:jazzy-ros-core-noble` |
| Immagine del progetto | `agirsailing:jazzy-desktop` | `agirsailing:jazzy-raspi` |
| Nome del container | `agir-ros-pc` | `agir-ros-raspi` |
| Cartelle condivise dall'host | `ros2_ws/src`, `scripts`, `tools`, `rosbags` | Tutta `ros2_ws` |

In entrambi i container l'utente è `ros` e il workspace si trova in `/home/ros/ros2_ws`. Questo percorso è interno al container: sull'host Raspberry la repository si trova invece in `/home/boat/2025_SOFTWARE/sailing_ros`.

### PC — Sviluppo e prove

Il [Dockerfile PC](pc_container/Dockerfile) parte dalla versione desktop di ROS Jazzy e aggiunge le librerie del progetto e gli strumenti di sviluppo. Contiene anche strumenti di visualizzazione e analisi, come RViz e PlotJuggler, utilizzabili quando è configurata la grafica.

Per costruire e avviare l'ambiente, dalla radice `sailing_ros`, esegui in **Git Bash su Windows** o nel **Terminale su macOS**:

```bash
bash Docker/pc_container/build.sh
```

Lo script usa il [Compose PC](pc_container/compose.yaml). L'avvio normale non richiede un server grafico né una GPU condivisa. La rete permette al container di collegarsi al broker MQTT e ai nodi ROS di comunicare al suo interno; per comunicare direttamente via ROS con altre macchine occorre configurare anche quel collegamento di rete.

Se vuoi aprire le finestre di RViz o di altri strumenti, prepara prima il server X sul PC e usa `bash Docker/pc_container/build.sh --gui`. Questa opzione aggiunge [compose.gui.yaml](pc_container/compose.gui.yaml) e usa il rendering software. I passaggi per collegare VS Code e compilare il codice sono nella [guida al settaggio PC](../guides/italiano/settaggio_pc.md).

### Raspberry — Esecuzione sulla barca

Il [Dockerfile Raspberry](raspi_container/Dockerfile) parte da ROS Core e aggiunge i pacchetti necessari al sistema: lettura seriale, I2C e GPIO, GPS, elaborazione, comunicazione MQTT e registrazione delle rosbag.

Il [Compose Raspberry](raspi_container/compose.yaml) condivide l'intero workspace e la cartella dei dispositivi `/dev`, rendendo disponibili al container anche le porte USB, la UART dell'IMU e il bus I2C. Usa la rete e lo spazio IPC dell'host, con esecuzione privilegiata per l'accesso hardware previsto dal progetto. La configurazione delle porte e dei permessi sull'host viene preparata dagli script di setup.

Per la prima installazione si usa `DAY_BEFORE_REGATTA/complete_setup.sh`; per gli aggiornamenti si usa `DAY_BEFORE_REGATTA/quick_setup.sh`. Questi script coordinano Docker e la compilazione ROS. Non serve avviare a mano i singoli passaggi Docker: la [guida al settaggio Raspberry](../guides/italiano/settaggio_raspberry.md) spiega la sequenza completa.

Il sistema può funzionare interamente tramite SSH, senza Wayland, X11 o una sessione desktop. L'avvio manuale passa da [`DAY_BEFORE_REGATTA/run.sh`](../DAY_BEFORE_REGATTA/run.sh); l'autostart si abilita separatamente dopo le prove.

## Cosa succede quando avvii il container

Gli script [entrypoint del PC](pc_container/entrypoint.sh) e [del Raspberry](raspi_container/entrypoint.sh) caricano ROS Jazzy, entrano nel workspace e caricano `install/setup.bash` se il codice è già stato compilato. Poi eseguono il comando ricevuto, oppure aprono Bash.

Avere il container acceso significa quindi avere l'ambiente disponibile, ma non significa che tutti i nodi della barca siano già in esecuzione. Sono tre passaggi distinti:

| Passaggio | Risultato |
|---|---|
| Costruire l'immagine e avviare il container | Prepara l'ambiente con ROS e le dipendenze. Sul PC lo fa `Docker/pc_container/build.sh`. |
| Compilare il workspace | Prepara pacchetti e messaggi del progetto. Nel container si esegue `bash scripts/build.sh` da `/home/ros/ros2_ws`. Sul Raspberry lo fanno già complete e quick. |
| Avviare il sistema ROS | Lancia i nodi. Sul Raspberry lo fa `DAY_BEFORE_REGATTA/run.sh`, eseguito sull'host. |

## Cosa rimane salvato e quando ricompilare

Sul PC, sorgenti, script, strumenti e rosbag rimangono nelle cartelle condivise dell'host. `build`, `install` e `log` restano invece nel container: fermarlo e riavviarlo li conserva, mentre ricrearlo li elimina e richiede una nuova compilazione. Sul Raspberry l'intero workspace è condiviso, quindi anche queste cartelle rimangono sull'host.

Se modifichi i sorgenti, usa gli [script del workspace](../ros2_ws/scripts/README.md) per ricompilare. Se aggiungi una libreria di sistema, aggiorna il Dockerfile dell'ambiente che la deve usare e ricostruisci l'immagine; se la libreria serve sia sul PC sia a bordo, aggiorna entrambi i Dockerfile. Una libreria installata manualmente solo in un container non entrerà automaticamente nella prossima immagine.

## Guide collegate

- [Configurazione del PC](../guides/italiano/settaggio_pc.md): avvio dell'ambiente, collegamento di VS Code e prima compilazione.
- [Configurazione del Raspberry](../guides/italiano/settaggio_raspberry.md): prima installazione, aggiornamenti e abilitazione dell'autostart.
- [Avvio del sistema ROS](../guides/italiano/avvio_sistema_ros.md): prove manuali e controlli del sistema sulla barca.
- [Script di bordo](../DAY_BEFORE_REGATTA/README.md): ruolo e configurazione di complete, quick, run e autostart.
