# Configurazione dell'ambiente di sviluppo sul PC

_Aggiornato al giorno: 30/10/2026_

[English](../inglese/pc_setup.md)

Questa guida spiega come avviare Docker, aprire la repository,
creare il container e collegarlo a VS Code. Si presuppone che tu abbia installato
i [software necessari](software_necessari.md), comprese le estensioni, e clonato
`sailing_ros` come indicato nel [README delle guide](../README.md).

## 1. Avvia Docker Desktop e apri la repository

1. Apri **Docker Desktop** e attendi l'avvio del motore.
2. Apri **Visual Studio Code**.
3. Seleziona **File > Open Folder…** e apri la tua cartella `sailing_ros`.

## 2. Apri il terminale del PC nella repository

Usa **Git Bash su Windows** (incluso in Git for Windows) oppure il **Terminale
su macOS**. In VS Code puoi selezionare il profilo Git Bash dal menu del terminale.
Questi comandi si eseguono sul PC, non dentro il container o in WSL.
Su Windows, se non sei già nella repository:

```bash
cd "/c/Users/ettor/Desktop/Agir_Sailing_Team/sailing_ros"
```

Su macOS usa il percorso del tuo clone, per esempio:

```bash
cd "$HOME/sailing_ros"
```

Sostituisci i percorsi con quelli del tuo computer. I comandi del prossimo
passaggio vanno eseguiti dalla **root di sailing_ros**, non da ros2_ws.

## 3. Costruisci e avvia il container

Su Windows e macOS basta eseguire:

```bash
bash Docker/pc_container/build.sh
```

Lo script costruisce l'immagine e crea o aggiorna il container `agir-ros-pc`
tramite Docker Compose. Attendi la fine della build: la prima esecuzione scarica
ROS e le dipendenze. L'avvio normale non richiede server X, GPU o configurazioni
grafiche del PC. Se sei già in `Docker/pc_container`, basta `bash build.sh`.
Puoi rieseguire lo stesso comando dopo modifiche al Dockerfile o al Compose.

**Grafica opzionale:** per aprire strumenti come RViz, prepara e avvia un server
X sul PC (per esempio VcXsrv su Windows o XQuartz su macOS), configurato per
ricevere le connessioni X11 via TCP dal container. Poi esegui:

```bash
bash Docker/pc_container/build.sh --gui
```

Questa opzione aggiunge [compose.gui.yaml](../../Docker/pc_container/compose.gui.yaml)
al [Compose di base](../../Docker/pc_container/compose.yaml), usando rendering
software senza montare la GPU. Non installa né configura il server X. Il display
predefinito è `host.docker.internal:0`; se il tuo server ne usa un altro, impostalo
per il comando, ad esempio `AGIR_DISPLAY=host.docker.internal:1 bash Docker/pc_container/build.sh --gui`.
Per tornare alla modalità normale, riesegui lo script senza `--gui`.

Se avevi creato `agir-ros-pc` con il vecchio comando `docker run`, Compose potrebbe
segnalare un nome già occupato. Verifica che sia il vecchio container di questo
clone, fermalo con `docker stop agir-ros-pc` e rinominalo con
`docker rename agir-ros-pc agir-ros-pc-previous` (scegli un nome libero), poi
riesegui `build.sh`. Il vecchio container rimane disponibile per recuperare file.

## 4. Controlla il container in Docker Desktop

Apri **Containers** e cerca **`agir-ros-pc`**. Deve risultare **Running**.
Se è fermo o Docker ha riportato un errore, controlla il terminale prima di
proseguire: la sola presenza del nome non conferma l'avvio.

## 5. Collega VS Code al container

1. Nella finestra VS Code del clone premi **Ctrl+Shift+P** su Windows o **Cmd+Shift+P** su macOS.
2. Seleziona **Dev Containers: Attach to Running Container…**.
3. Scegli **`agir-ros-pc`**.
4. Attendi la nuova finestra collegata al container.

La funzione è fornita da Dev Containers, incluso in Remote Development.
Riferimento: [guida ufficiale VS Code](https://code.visualstudio.com/docs/devcontainers/attach-container).

## 6. Apri il workspace e compila

Nella **nuova finestra**, apri la cartella `/home/ros/ros2_ws`, poi **Terminal > New Terminal**.
Il terminale è ora Bash **nel container**, anche se il PC è Windows. Verifica:

```bash
pwd
```

Il risultato deve essere `/home/ros/ros2_ws`. Per compilare:

```bash
bash scripts/build.sh --clean
source install/setup.bash
```

Per i launch di comunicazione prepara prima `src/communication_web/config/mqtt_config.yaml`
dal modello nella stessa cartella e compila entrambi i gateway. I test con MQTT
simulato non richiedono credenziali reali. Build, test e argomenti sono spiegati
nel [README degli script](../../ros2_ws/scripts/README.md).

Entrambe le modalità condividono con il PC `src`, `scripts`, `tools` e `rosbags`.
`build`, `install` e `log` restano nel container: se viene ricreato, ricompila
il workspace. Non trasferire questi prodotti di build al Raspberry.
La rete predefinita permette MQTT in uscita e comunicazione ROS tra nodi nello
stesso container; il collegamento ROS diretto ad altri computer richiede una
configurazione di rete dedicata.
Per fermare il container, dal terminale del PC: `docker stop agir-ros-pc`.
Per riutilizzarlo senza cambiare modalità: `docker start agir-ros-pc`, poi collega
nuovamente VS Code. Per aggiornarlo o cambiare modalità usa `build.sh`.
