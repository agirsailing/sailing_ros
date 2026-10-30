# Strumenti del workspace

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../../README.md)

## Generazione degli endpoint

[gen_endpoints.py](gen_endpoints.py) legge `src/**/config/endpoints.yaml`, risolve
i riferimenti `@...` e genera i moduli Python/header C++ richiesti da
`meta.generate`. È richiamato dagli script di build/test. Esecuzione manuale nel
container, dalla root del workspace:

```bash
python3 tools/gen_endpoints.py
```

Modificare gli YAML sorgenti, non correggere a mano i file generati. Dopo un
cambio topic aggiornare anche consumer, documentazione, test e contratti MQTT se
coinvolti. Il generatore non crea automaticamente subscriber/publisher nel codice.

## Esportazione di tutte le rosbag in CSV

[allbags_to_csv.py](allbags_to_csv.py) esporta **tutti i topic presenti nelle bag**,
senza preset, filtri o nomi fissati nel codice. Converte registrazioni già esistenti;
non avvia la registrazione e non richiede il replay o i nodi live.

Nel container ROS, dalla root del workspace compilato:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 tools/allbags_to_csv.py /percorso/registrazioni --output-dir /percorso/csv
```

Sostituire i percorsi con quelli accessibili nel container. Il primo argomento può
essere una singola bag con `metadata.yaml` oppure la cartella che contiene le bag
(ricerca nel primo livello). Sono riconosciute anche le cartelle `rosbag2_*`.
Senza `--output-dir` l'output va nella directory corrente. Per ogni bag crea una
sottocartella con lo stesso nome, senza l'eventuale prefisso `rosbag2_`.

- Un CSV per topic, anche se non contiene campioni; topic con nomi simili ricevono
  suffissi diversi per evitare collisioni tra file.
- `timestamp_ns` è il timestamp della registrazione nella bag, in nanosecondi.
  L'eventuale timestamp del messaggio rimane in `header.stamp.sec` e
  `header.stamp.nanosec`. Un campo custom chiamato `timestamp_ns` diventa
  `message.timestamp_ns` per non sovrascrivere quello della bag.
- Campi annidati in colonne come `orientation.x`; array e sequenze di messaggi
  conservati in celle JSON, anche quando cambiano lunghezza.
- Usa i tipi ROS disponibili nell'ambiente, compresi quelli custom del workspace;
  non serve pandas. Supporta gli storage ROS installati, inclusi MCAP e SQLite3.
- Una nuova esportazione sovrascrive i CSV omonimi: usare una cartella di output
  distinta per ogni analisi. Gli errori producono un codice di uscita diverso da zero;
  eventuali file parziali di una bag fallita non vanno considerati completi.

Test su bag temporanee MCAP/SQLite3: `python3 -m pytest tools/tests/test_allbags_to_csv.py`.

## Utilità legacy

[gen_bag_test.py](gen_bag_test.py) simula vecchi topic `/serial/raw_rx`, `/gps_data`
e `/gps_vel_data`: non è adattato agli attuali messaggi Agir.
Per registrare e ispezionare le bag usare il [README rosbag_manager](../src/rosbag_manager/README.md).
La diagnostica MQTT indipendente da ROS è in [tools/mqtt_diagnostics](../../tools/mqtt_diagnostics/README.md).
