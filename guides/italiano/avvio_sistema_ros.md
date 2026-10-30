# Avvio del sistema ROS sul Raspberry Pi

_Aggiornato al giorno: 30/10/2026_

[English](../inglese/ros_system_startup.md)

Questa guida descrive come avviare il sistema ROS sul Raspberry Pi e usare alcuni comandi per verificarne il funzionamento.

Si presuppone che il codice sia già presente sul Raspberry e che la configurazione sia stata completata seguendo la [guida alla configurazione del Raspberry](settaggio_raspberry.md).

L'avvio dipende da due casi: **autostart non abilitato**, con avvio manuale, oppure **autostart abilitato**, con avvio automatico all'accensione.

## Verificare lo stato dell'autostart

Dal terminale del PC, collegati al Raspberry seguendo la [guida alla connessione](connessione_raspberry.md):

```text
ssh boat@boat.local
```

Nel **terminale SSH del Raspberry**, controlla se il servizio è abilitato all'avvio:

```bash
systemctl is-enabled agir_regatta.service
```

- `enabled`: l'autostart è abilitato.
- `disabled`: il servizio è installato, ma l'autostart non è abilitato.
- `not-found` oppure un messaggio che indica che il servizio non esiste: l'autostart non è installato; usa l'avvio manuale.

Se compare `masked` o un altro errore, verifica la configurazione del servizio prima di procedere.

Se il servizio è installato, controlla anche se è attualmente in esecuzione:

```bash
systemctl is-active agir_regatta.service
```

`active` indica che il servizio è in esecuzione, `inactive` che è fermo e `failed` che si è verificato un errore. L'abilitazione all'avvio e lo stato attuale sono due informazioni diverse: un servizio può essere abilitato ma fermo, oppure disabilitato ma ancora in esecuzione.

Se il servizio è già `active`, passa ai comandi di debug senza avviare una seconda copia del sistema. Lo stato `active` da solo non garantisce che tutti i nodi ROS siano già pronti.

## Caso 1 — Autostart non abilitato

Per avviare manualmente il sistema, nel **terminale SSH del Raspberry** entra nella cartella `DAY_BEFORE_REGATTA`, rendi eseguibile [`run.sh`](../../DAY_BEFORE_REGATTA/run.sh) e avvialo:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros/DAY_BEFORE_REGATTA
chmod +x run.sh
./run.sh
```

Lo script avvia il container **`agir-ros-raspi`** e il sistema ROS al suo interno. Mantieni aperto questo terminale per seguire i messaggi durante l'esecuzione; usa un secondo terminale per i controlli.

All'avvio, lo script attende che il Raspberry riesca a raggiungere `8.8.8.8` tramite ping, salvo diversa configurazione. Se resta sul messaggio di attesa della rete, verifica che il Raspberry abbia accesso a Internet e che il ping non sia bloccato.

## Caso 2 — Autostart abilitato

Se l'autostart è abilitato, ROS si avvia automaticamente all'accensione del Raspberry tramite **`agir_regatta.service`**. Non occorre eseguire manualmente `run.sh`.

Puoi controllare lo stato del servizio dal **terminale SSH del Raspberry**:

```bash
systemctl status agir_regatta.service --no-pager
```

Anche l'avvio automatico attende la disponibilità della rete, come descritto nel caso manuale.

Se il servizio è fermo, per esempio dopo un aggiornamento con `quick_setup.sh`, avvialo senza riavviare il Raspberry:

```bash
sudo systemctl start agir_regatta.service
```

Per abilitare l'autostart, segui la sezione dedicata nella [guida alla configurazione del Raspberry](settaggio_raspberry.md#abilitare-lautostart).

## Comandi utili per il debug

Apri **un altro terminale sul PC** e collegati al Raspberry con una seconda sessione SSH:

```text
ssh boat@boat.local
```

### Vedere i container in esecuzione

Nel **terminale SSH del Raspberry**:

```bash
docker ps
```

Nella colonna `NAMES` cerca `agir-ros-raspi`. La presenza del container indica che è in esecuzione; per verificare ROS usa i comandi seguenti.

### Entrare nel container

Apri una shell nel container già avviato:

```bash
docker exec -it agir-ros-raspi bash
```

Da questo momento i comandi vengono eseguiti **dentro il container**. Carica l'ambiente ROS e la workspace:

```bash
source /opt/ros/jazzy/setup.bash
source /home/ros/ros2_ws/install/setup.bash
```

### Elencare i nodi ROS

```bash
ros2 node list
```

Mostra i nodi ROS visibili nella sessione.

### Elencare i topic ROS

```bash
ros2 topic list
```

Mostra i topic ROS disponibili.

### Leggere i messaggi di un topic

```bash
ros2 topic echo <nome_del_topic>
```

Sostituisci `<nome_del_topic>`, comprese le parentesi angolari, con un nome restituito da `ros2 topic list`. Il comando mostra i messaggi man mano che vengono pubblicati. Premi `Ctrl+C` per interrompere la lettura.

Per uscire dalla shell del container e tornare al terminale del Raspberry, esegui `exit`: questo non arresta il sistema ROS.

### Leggere i log dell'autostart

Se il sistema è avviato tramite il servizio, dal **terminale SSH del Raspberry, fuori dal container**, puoi leggere gli ultimi messaggi e seguirne i nuovi:

```bash
sudo journalctl -u agir_regatta.service -n 100 -f
```

Premi `Ctrl+C` per interrompere la visualizzazione dei log.



### Leggere una misura e controllare gli hertz

Nel container:

```bash
ros2 topic echo /ultrasonic/left --field range
```

Interrompi con Ctrl+C, poi prova:

```bash
ros2 topic hz /imu/data
```

Per fermare il sistema, termina prima la registrazione dalla webapp o dal servizio
ROS. Poi, dall'host Raspberry nella root della repository:

```bash
sudo systemctl stop agir_regatta.service
docker compose -f Docker/raspi_container/compose.yaml stop
```

Il primo comando serve solo se il servizio è installato. Chiudere SSH o uscire
dal container non garantisce l'arresto dei processi ROS.
