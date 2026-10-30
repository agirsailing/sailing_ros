# Diagnostica MQTT senza sensori

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../../README.md)

[probe.py](probe.py) crea un publisher sintetico e due osservatori, TCP e
WebSocket, con identificativi client distinti. Serve a isolare trasporto/broker
dal runtime ROS. Non legge sensori e non implementa servizi di registrazione o
ping boe. Il test con browser aperto aggiunge la verifica visiva della webapp.

## Raspberry via SSH: un comando

Prerequisiti: repository aggiornata, runtime reale fermo, file privato
`ros2_ws/src/communication_web/config/mqtt_config.yaml` compilato. Dall'host Pi:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros/tools/mqtt_diagnostics
bash run.sh webapp --dashboard-hz 3 --map-hz 3 --state-hz 0.5
```

Il wrapper prepara Python/venv e dipendenze (può chiedere sudo per apt su Debian),
crea `config.local.json` da `config.ros.example.json` se manca e riutilizza broker,
porta TCP, TLS e credenziali dello YAML ROS. Non occorre Docker per questo test.
I parametri WebSocket vengono dal JSON: default porta **8084**, path **/mqtt**;
verificare che corrispondano al proprio endpoint. Un JSON già presente non viene
sovrascritto, quindi controllarne eventuali override.

Aprire una webapp senza Demo, fare login e osservare ULTRASONIC LEFT/RIGHT per
tutta la prova. I valori cambiano a ogni messaggio dashboard. La durata è 900 s.
Annotare orari UTC di ritardi/disconnessioni, rete/hotspot usato, numero di tab e
client attivi; non cambiare più variabili nello stesso confronto.

**Frequenze:** il comando sopra riproduce le attuali frequenze nominali ROS→MQTT,
3+3+0.5 = 6.5 pubblicazioni/s. `bash run.sh` senza opzioni usa invece dashboard
5 Hz, mappa 2 Hz, stato 0.5 Hz (7.5/s). Questo non riproduce l'acquisizione ROS
né garantisce payload/carico identici. Il pattern ramp cambia di 2 cm per messaggio;
il suo periodo cambia aumentando gli hertz.

## Windows: cmd, senza container ROS

Installare Python 3.10+ con il launcher `py` se assente. Aprire cmd:

```bat
cd /d C:\Users\ettor\Desktop\Agir_Sailing_Team\sailing_ros\tools\mqtt_diagnostics
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Solo se non esiste ancora `config.local.json`:

```bat
copy config.ros.example.json config.local.json
```

Con MQTT YAML ROS configurato e publisher reali fermi:

```bat
.venv\Scripts\python.exe probe.py --config config.local.json --ros-config ..\..\ros2_ws\src\communication_web\config\mqtt_config.yaml --duration 900 --dashboard-hz 3 --map-hz 3 --state-hz 0.5 --ultrasonic-pattern ramp --webapp
```

Nel JSON basato su ROS `publisher` può rimanere `{}`. Gli osservatori ereditano
le credenziali del publisher, salvo override espliciti. Senza YAML usare
[config.example.json](config.example.json), compilare host/porte/TLS e fornire
`MQTT_USER`/`MQTT_PASSWORD` tramite ambiente o prompt. Non committare segreti.

## Modi e isolamento

| Comando Bash | Comportamento |
|---|---|
| `bash run.sh setup` | Prepara solo ambiente Python |
| `bash run.sh webapp ...` | Prepara ambiente e pubblica su topic reali `agir_gui/data/...` |
| `bash run.sh cloud --ros-config ../../ros2_ws/src/communication_web/config/mqtt_config.yaml` | Usa config.local.json, topic isolati; fare setup prima |
| `bash run.sh local --duration 900` | Avvia Mosquitto Docker e usa local.json; fare setup prima |
| `bash run.sh local-logs` | Log del broker locale |
| `bash run.sh local-down` | Ferma il broker locale |
| `bash run.sh analyze runs/NOME_RUN` | Rigenera analisi da file salvati |

Per cloud isolato creare prima il JSON locale come sopra. Senza `--webapp`, i
topic sono `agir_diag/<run_id>/...`; il browser di produzione non li vede.
Il probe diretto ha default 2/2/0.5 Hz e pattern step ogni 5 s: specificare ramp
per variazioni a ogni messaggio. `--qos 0|1`, `--protocol 311|5`, `--decimals N`
permettono confronti controllati; decimals non arrotonda coordinate/timestamp.
Le ACL devono consentire i topic del test. Non avviare simulatori e barca reale
sugli stessi topic contemporaneamente.

Mosquitto locale espone TCP `127.0.0.1:18883`, WS `127.0.0.1:19001`, senza TLS.
Una webapp HTTPS configurata per WSS cloud non usa automaticamente quel broker.
Un successo locale non certifica EMQX, hotspot o rendering browser.

## Risultati e interpretazione

Ogni prova crea `runs/<data-id>/`:

| File | Contenuto |
|---|---|
| `run.json` | Metadati e parametri della prova, senza credenziali |
| `events.jsonl` | Connessioni, disconnessioni, invii ed errori con orari UTC |
| `samples.csv` | Campioni ricevuti, sequenze, dimensioni, latenze |
| `summary.json` | Metriche strutturate per osservatore/stream |
| `report.md` | Riepilogo leggibile |

Confrontare durata effettiva, Hz osservati, sequenze uniche/duplicati, gap massimo,
p50/p95/max e mediana primo/ultimo minuto. La latenza è dal publish sintetico
al callback Python, sullo stesso clock monotono: **non misura il rendering del
browser**. Un invio accettato dal client non prova consegna, soprattutto con QoS 0.
Controllare anche stream mancanti e disconnessioni; assenza di campioni non è successo.

Se la prova si interrompe, conservare tutta la cartella e usare analyze. Copiare
dal Pi al PC la cartella della run, non la `.venv`. Per correlare con EMQX usare
UTC/client ID/reason code; un errore di trasporto generico non prova un limite del
piano. [VALIDATION.md](VALIDATION.md) conserva una verifica storica del tool,
non certifica l'attuale configurazione della barca.
