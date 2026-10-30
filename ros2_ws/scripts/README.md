# Script del workspace

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../../README.md)

Eseguire nel container ROS, dalla directory `/home/ros/ros2_ws`. Questi script
non installano Docker, non aggiornano Git e non configurano l'hardware dell'host.

| Script | Uso | Comportamento |
|---|---|---|
| [build.sh](build.sh) | `bash scripts/build.sh --clean` | Default pulito: rimuove build/install/log, genera endpoint, compila interfacce e workspace |
| [build.sh](build.sh) | `bash scripts/build.sh --incremental` | Riutilizza build/install; adatto a modifiche ordinarie dei sorgenti |
| [run.sh](run.sh) | `bash scripts/run.sh live` | Carica gli ambienti e lancia orchestrator; richiede una build esistente |
| [run.sh](run.sh) | `bash scripts/run.sh replay` | Avvia elaborazione e telemetria con tempo simulato; sorgenti fornite da ros2 bag play |
| [test.sh](test.sh) | `bash scripts/test.sh` | Build incrementale e tutti i test |
| [test.sh](test.sh) | `bash scripts/test.sh --no-build sensors sail_common` | Test dei soli pacchetti indicati, senza build |
| [test.sh](test.sh) | `bash scripts/test.sh --clean-build --summary` | Build pulita e riepilogo compatto |

`PARALLEL_WORKERS` ha default 2. Esempio:

```bash
PARALLEL_WORKERS=2 bash scripts/build.sh --incremental
bash scripts/test.sh --no-build data_elaboration communication_web
```

Con pacchetti indicati, la build incrementale di test.sh compila quei pacchetti
e le loro dipendenze; `--clean-build` ricompila invece tutto il workspace.
In entrambi i casi esegue i test solo dei pacchetti selezionati.
Con `--no-build` assicurarsi che i sorgenti corrispondano alla build.
Controllare i risultati XML: uno skip non prova un comportamento. I test di
parser/freschezza/geometria non certificano sensori, rete o calibrazione reali.
Le sezioni seguenti descrivono le prove sul sistema.

Per aggiungere test, seguire i test già presenti nel pacchetto: pytest per Python,
ament/GTest dove previsto. Dichiarare dipendenze di test in package.xml e registrare
i test nel sistema di build. Isolare driver/broker con fake nei test unitari;
provare separatamente integrazione ROS e hardware. Coprire soprattutto dati
scaduti, mancanti, clock che torna indietro, input malformati e confini geometrici.

Gli argomenti dopo `live`/`replay` sono inoltrati a ros2 launch. Il modo
`bag_full_topic` è un placeholder non configurato. Non confondere questo run.sh
con quello host in DAY_BEFORE_REGATTA o quello della diagnostica MQTT.

## 1. Controlli sul PC, nel container ROS

```bash
cd /home/ros/ros2_ws
bash scripts/test.sh --clean-build
bash scripts/test.sh --no-build communication_web sail_common
colcon test-result --verbose
```

La prima riga di test ricompila da zero ed esegue tutti i test; la seconda è
l'alternativa mirata dopo una build già valida. Non occorre eseguirle entrambe
per ogni modifica. Errori di lint sono distinti dai test funzionali; leggi il
riepilogo e gli XML, non soltanto l'ultima riga del terminale. Uno skip non è un
pass e va motivato. `--no-build` non rigenera interfacce mancanti.

I test coprono decoder, geometria, cache/freschezza, lifecycle rosbag e gateway.
Le prove `test_*pipeline_ros.py` usano ROS/DDS reali nel container ma mockano
hardware o MQTT: non sono una prova di EMQX o del cablaggio. I test shell di
deployment usano copie temporanee e comandi amministrativi simulati.

## 2. Solo webapp — PC, terminale nella repository web

```powershell
node --test test/*.test.js
```

Quando cambi un contratto MQTT verifica entrambe le repo: nomi, campi, unità,
null/NaN, frequenze, timeout, ruoli e comportamento dopo disconnessione.

## 3. Raspberry e barca

Segui le [prove manuali](../../guides/italiano/avvio_sistema_ros.md), annota commit, YAML installati,
cablaggio, rete e risultato. Verifica frequenze con `ros2 topic hz`, ma anche
timestamp unici: ricevere 50 messaggi/s non prova 50 misure nuove.
Prova la perdita di una sorgente e il recupero senza inventare dati freschi.

## Criteri per una PR

- Comportamento e parametri spiegati nel README del pacchetto.
- Test pertinenti superati e limiti hardware dichiarati.
- Nuove interfacce registrate in CMake, dipendenze nei package.xml/Dockerfile.
- Endpoint rigenerati e consumer aggiornati, compresa la webapp se necessario.
- Nessun token/config privato, `.venv`, build/install/log o bag nel commit.
- Per un bug registra il prima/dopo e la prova che lo riproduce, non solo test
  che ripetono i dettagli dell'implementazione.
