# MQTT diagnostics without ROS or a Raspberry

Questo test gira sul PC. Un client simula il gateway della barca e pubblica
dashboard, mappa e stato registrazione. Due client indipendenti ricevono gli
stessi messaggi: uno via MQTT nativo, l'altro via WebSocket. Non richiede ROS,
sensori o browser. Usa MQTT 3.1.1, QoS 0 e keepalive 60 s come la telemetria
attuale; `--protocol 5` permette una prova separata con motivi di distacco più
dettagliati quando il broker li fornisce.

Per default la distanza simulata passa tra 0,50 e 0,80 m ogni 5 secondi. La mappa simula un
percorso. I timestamp sono reali e i flag di validità sono true.

## Installazione sul PC

### Comando breve e prova sul Raspberry via SSH

`bash run.sh` avvia direttamente una prova di 15 minuti con webapp, ultrasuoni
diversi a ogni messaggio, dashboard a 5 Hz, mappa a 2 Hz e stato ogni 2 secondi.
Legge il YAML MQTT del package; se manca `config.local.json`, lo crea dal modello
`config.ros.example.json` usando le stesse credenziali per tutti i client.
Il modello usa WSS sulla porta 8084 con percorso `/mqtt`: adattare il JSON locale
se il deployment usa valori diversi. Un JSON locale esistente non viene sovrascritto.

Flusso di deploy: dal PC fare commit/push su `dev` e merge su `main`.
Sul Raspberry già configurato per aggiornare da `main`, via SSH e fuori dal container:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/quick_setup.sh
```

Se il quick termina correttamente, lascia il container ROS fermo. Non avviare il
`run.sh` della regata. Non è necessario installare l'autostart per questo test.
Usare il `mqtt_config.yaml` locale del Raspberry già compilato con broker e
credenziali reali. Poi basta un solo comando, anche alla prima esecuzione:

```bash
bash tools/mqtt_diagnostics/run.sh
```

Il launcher crea automaticamente la `.venv` sul Raspberry e installa le dipendenze.
Su Raspberry Pi OS/Debian installa anche `python3` e `python3-venv` se mancanti:
può chiedere la password sudo dell'utente del Raspberry. La prima preparazione
richiede Internet. Le esecuzioni successive riutilizzano l'ambiente e installano
dipendenze solo se mancanti o di versione diversa da `requirements.txt`.
Non copiare o committare la `.venv` Windows: contiene eseguibili specifici del PC.
`bash run.sh setup` rimane disponibile per preparare soltanto l'ambiente.

Apri la webapp sul PC, senza Demo. Mantieni la connessione SSH aperta; risultati
in `tools/mqtt_diagnostics/runs/` sul Raspberry. Il launcher non avvia o ferma
automaticamente ROS e non modifica frequenze o configurazioni della barca.
Per confrontare a 2 Hz, dalla root del repository:

```bash
bash tools/mqtt_diagnostics/run.sh webapp --dashboard-hz 2
```

Sul PC Windows il launcher si usa da Git Bash; i comandi Python diretti sotto
restano disponibili per CMD e PowerShell.

Requisiti: Python 3.10+; Docker Desktop solo per il broker locale. Non serve
Docker per provare EMQX. Le dipendenze Python sono installate in `.venv`.

Da **Git Bash sul PC Windows**, nella root di `sailing_ros`:

```bash
cd tools/mqtt_diagnostics
# Su Windows, se python3 non esiste, usa MQTT_TEST_PYTHON=python.
MQTT_TEST_PYTHON=python bash run.sh setup
```

Su Linux/WSL/macOS con Python 3 disponibile: `bash run.sh setup`.

Alternativa **PowerShell**, sempre dalla root di `sailing_ros`:

```powershell
cd tools/mqtt_diagnostics
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nei comandi seguenti `bash run.sh cloud ...` equivale, in PowerShell, a:

```powershell
.\.venv\Scripts\python.exe probe.py --config config.local.json ...
```

## Prova locale: controllo senza Internet né limiti di un piano cloud

Avvia Docker Desktop, poi in Git Bash:

```bash
bash run.sh local --duration 900 --dashboard-hz 20 --map-hz 5 --state-hz 1
```

Oppure in PowerShell:

```powershell
docker compose up -d broker
.\.venv\Scripts\python.exe probe.py --config local.json --duration 900 --dashboard-hz 20 --map-hz 5 --state-hz 1
```

Il broker di prova è Mosquitto, senza autenticazione, esposto **solo sul PC**:
TCP `127.0.0.1:18883`, WebSocket `127.0.0.1:19001`. Non modificare il binding
in `0.0.0.0`. Non è una configurazione di produzione. In locale il test usa
TCP/WS senza TLS; sul cloud usa TLS/WSS con verifica del certificato.

Il broker rimane avviato per le prove successive. Per conservarne i log e fermarlo:

```bash
bash run.sh local-logs > runs/local-broker.log
bash run.sh local-down
```

In PowerShell: `docker compose logs --timestamps broker` e `docker compose down`.
La webapp attuale accetta solo WSS: il broker locale WS serve al test Python;
non disabilitare la verifica TLS della webapp per collegarla qui.

## Configurazione EMQX o altro broker cloud

```bash
cp config.example.json config.local.json
```

In PowerShell: `Copy-Item config.example.json config.local.json`.

Nel file configura host, porta MQTT/TLS e porta/path WebSocket usando **i dati
del tuo deployment**. Le porte dell'esempio non sostituiscono quelle della console.
Il file locale è ignorato da Git. Username e password vengono richiesti dal test
(password nascosta), oppure letti dalle variabili `MQTT_USER` e `MQTT_PASSWORD`.
Non passare password come argomenti della riga di comando.

Puoi riutilizzare le credenziali della barca già presenti sul PC:

```bash
bash run.sh cloud --ros-config ../../ros2_ws/src/communication_web/config/mqtt_config.yaml --duration 900
```

Questo riusa host, porta TCP, TLS, CA e credenziali del gateway. La configurazione
del subscriber WebSocket continua a provenire dal JSON. Per credenziali di lettura
separate, aggiungi a ciascun subscriber `"username_env": "MQTT_SUB_USER"` e
`"password_env": "MQTT_SUB_PASSWORD"`. Il test chiederà anche questi valori.

**Topic predefiniti isolati:** `agir_diag/<run_id>/dashboard`, `/map` e
`/recording_state`. Nel broker autorizza la pubblicazione e la sottoscrizione
su `agir_diag/#` per gli account di prova. Un account autorizzato soltanto a
`agir_gui/data/#` non basta. Il test attende CONNACK e SUBACK e segnala rifiuti
o assenza di messaggi, anziché dichiarare un successo vuoto.

Non cambiamo configurazioni o piani cloud automaticamente. Il test pubblica
dati solo quando viene eseguito da te. Le prove sopra quota sono limitate alla
durata indicata e possono subire throttling/disconnessioni o consumare traffico
del deployment: fanno parte della misura, non sono un modo per aggirare limiti.

## Sequenza di confronto (una prova per volta)

Ferma i publisher reali della barca durante il confronto, così non sommi altro
traffico sullo stesso deployment. Mantieni rete e configurazione uguali fra le
prove; annota piano EMQX, eventuali altri client, VPN/hotspot e rete utilizzata.

1. Configurazione attuale, 4,5 pubblicazioni/s:

   ```bash
   bash run.sh cloud --duration 900 --dashboard-hz 2 --map-hz 2 --state-hz 0.5
   ```

2. Configurazione precedente, 10 pubblicazioni/s:

   ```bash
   bash run.sh cloud --duration 900 --dashboard-hz 4 --map-hz 4 --state-hz 2
   ```

3. Frequenza desiderata, 26 pubblicazioni/s (supera il limite documentato per
   client di EMQX Serverless; usa un broker/piano adeguato per aspettarti successo):

   ```bash
   bash run.sh cloud --duration 900 --dashboard-hz 20 --map-hz 5 --state-hz 1
   ```

4. Ipotesi decimali: ripeti **la stessa prova che fallisce**, aggiungendo
   `--decimals 2`. Cambia solo la precisione dei numeri dashboard; non coordinate,
   timestamp, numero di topic o frequenze. Confronta i byte medi effettivamente
   misurati e il tempo al primo distacco, non solo l'impressione visiva.

Ogni processo genera un nuovo run_id e client ID. Una sola connessione pubblica
tutti e tre i topic, come il gateway reale. Non creiamo più publisher per eludere
limiti per client. Il generatore salta gli slot persi durante ritardi/disconnessioni
e non produce raffiche per recuperare il passato.

## Provare anche la webapp, senza Raspberry

Con i publisher reali **fermi**, usa il broker cloud e gli stessi topic della GUI:

```bash
bash run.sh cloud --webapp --duration 900 --dashboard-hz 2 --map-hz 2 --state-hz 0.5
```

Apri la webapp normalmente e collegala al medesimo broker. **Non usare Demo**:
ora i dati simulati arrivano davvero via MQTT. Non premere i comandi di
registrazione: il simulatore non offre servizi e non risponde ai comandi.
I dati di prova sostituiscono la telemetria su `agir_gui/data/*` per tutti gli
operatori collegati; non eseguire questa modalità durante una sessione reale.
La chiave JSON aggiuntiva `_probe` serve alla misura ed è ignorata dalla GUI.

Per una prova pulita, chiudi gli altri client e apri solo una webapp. Registra
anche `JSON.stringify(window.agirDiagnostics(), null, 2)` quando rallenta, se
hai pubblicato la versione della webapp che espone questa diagnostica.

## Ultrasuoni diversi a ogni messaggio: confronto dal PC con webapp

Usa `--ultrasonic-pattern ramp`: il sinistro sale da 0,50 a 0,80 m e poi scende,
cambiando di 0,02 m a ogni messaggio dashboard. Il destro segue con +0,03 m.
Anche l'altezza simulata segue il movimento. Il cambiamento resta visibile con
due decimali. È un segnale diagnostico, non un modello fisico della barca:
il ciclo dura 30 messaggi (15 s a 2 Hz, 6 s a 5 Hz).
La modalità precedente resta disponibile come `--ultrasonic-pattern step`.
La modalità scelta compare nel terminale, in `run.json`, `summary.json` e `report.md`.

Sul PC già preparato, dalla cartella `tools/mqtt_diagnostics`, questi comandi
funzionano sia in CMD sia in PowerShell. Riutilizzano `config.local.json` e le
credenziali nel YAML del package. Non serve Docker o il Raspberry.
Ferma i publisher reali: `--webapp` invia dati sui topic reali, visibili agli
operatori collegati. Apri una sola webapp, senza Demo e senza usare la registrazione.

1. Prima prova, stessi Hz delle prove precedenti (4,5 publish/s totali):

   ```text
   .venv\Scripts\python.exe probe.py --config config.local.json --ros-config ..\..\ros2_ws\src\communication_web\config\mqtt_config.yaml --duration 900 --dashboard-hz 2 --map-hz 2 --state-hz 0.5 --ultrasonic-pattern ramp --webapp
   ```

2. Quando la prima prova è finita, se è stabile, ricarica la webapp per iniziare
   dal medesimo stato iniziale e avvia la seconda: aumenta solo la dashboard a
   5 Hz (7,5 publish/s totali). Mappa e stato registrazione restano invariati.

   ```text
   .venv\Scripts\python.exe probe.py --config config.local.json --ros-config ..\..\ros2_ws\src\communication_web\config\mqtt_config.yaml --duration 900 --dashboard-hz 5 --map-hz 2 --state-hz 0.5 --ultrasonic-pattern ramp --webapp
   ```

Non avviare le prove contemporaneamente. Lascia la scheda visibile e il PC
senza sospensione per 15 minuti. Annota l'orario di blocchi, ritardi crescenti o
disconnessioni e confrontalo con i client `up/down` nel terminale. Durante una
prova non ricaricare la pagina. Ogni comando crea una nuova cartella in `runs`.
I valori `—` dopo la fine dell'invio sono previsti. Questi test misurano il
trasporto nei ricevitori Python: serve anche l'osservazione della webapp.

## File prodotti e lettura dei risultati

Ogni esecuzione crea `runs/<timestamp>-<run_id>/`:

- `report.md`: tabella leggibile con frequenza **effettivamente ricevuta**, p50,
  p95 e massimo della latenza, confronto primo/ultimo minuto e massimo intervallo
  senza messaggi per ogni osservatore/topic.
- `summary.json`: stessi risultati e dettagli dei distacchi/errori.
- `events.jsonl`: eventi con UTC, client ID, motivi di disconnessione,
  connessione/SUBACK, ping, tentativi di pubblicazione e codici di ritorno.
- `samples.csv`: un record per messaggio ricevuto, sequenza, byte e latenza.
- `run.json`: frequenze, protocollo e metadati della prova; niente credenziali.

Mandaci l'intera cartella della prova. Non includere `config.local.json`, `.venv`
o `mqtt_config.yaml`. I report non copiano password, username, broker host o
payload completi. Usa `--output runs/nome-prova` per un nome scelto; una directory
già esistente viene rifiutata per evitare sovrascritture.

Con Ctrl+C viene comunque generato il report. Se il processo viene terminato
forzatamente, puoi rigenerarlo dai file già scritti:

```bash
bash run.sh analyze runs/NOME-DELLA-PROVA
```

Codici di uscita: 0 prova terminata senza distacchi/errori rilevati, 2 errori,
distacchi inattesi o nessuna ricezione, 130 interruzione con Ctrl+C. Il codice 0
non certifica latenza bassa: controlla i numeri e le sequenze nel report.

Interpretazione:

| Risultato | Indagine successiva |
|---|---|
| Locale stabile, cloud lento su entrambi gli osservatori | Broker/piano o rete verso il cloud; non richiede il browser per riprodursi |
| TCP stabile, WebSocket lento | Percorso/listener WebSocket o rete/proxy specifici; controllare gli eventi |
| Entrambi gli osservatori stabili, sola webapp lenta | Browser, MQTT.js, rendering o percorso di rete del browser |
| Anche il locale lento | PC, Docker, carico o strumento di prova; non attribuirlo al cloud |
| Problema scompare cambiando rete con stesso broker e stessa prova | Rete originaria fortemente sospetta |

La latenza usa lo stesso clock monotono per invio e ricezione: non dipende dalla
sincronizzazione PC/Raspberry. Misura generazione → callback Python e include
scheduling locale, non il rendering del browser. Il subscriber WebSocket è Paho,
non MQTT.js. Un publish accettato dal client non garantisce consegna; il callback
di completamento QoS 0 non è un ACK del broker. La pausa finale di svuotamento è
limitata a 2 s: eventuali messaggi ancora in coda possono mancare dai ricevuti.

## EMQX e limiti di frequenza

Nella documentazione consultata il 15 ottobre 2026, EMQX Serverless indica
10 publish/s **per client**, non modificabili; Dedicated Flex/BYOC indica un
limite predefinito più alto (1500/s) e configurabile. Un conto è la dimensione
del JSON, un altro il numero di pubblicazioni. Verifica il piano effettivo prima
di applicare questi numeri al tuo deployment.

Con dashboard e mappa entrambe a 20 Hz e stato a 1 Hz, una singola connessione
produce 41 publish/s: serve un broker/piano adatto. Il Mosquitto locale è un
controllo utile; per accesso remoto servono hosting, TLS/WSS, autenticazione e ACL.
Una dashboard a 20 Hz non richiede necessariamente una mappa a 20 Hz.

Un distacco anche a 4,5 publish/s non è spiegato dal semplice superamento dei
10 publish/s: raccogliere eventi, verificare frequenze reali e confrontare reti.
EMQX distingue Logs e Log Trace: quest'ultimo è disponibile soltanto su determinati
piani/versioni. L'assenza del menu Trace non dimostra un errore dell'operatore.

Fonti:
- https://docs.emqx.com/en/cloud/latest/create/restriction.html
- https://docs.emqx.com/en/cloud/latest/deployments/log_trace.html
- https://docs.emqx.com/en/cloud/latest/deployments/logs.html

## Test dello strumento

```bash
python -m unittest discover -s tests -v
```

I test offline coprono payload, analisi, eventi di errore e protezione delle
credenziali. Per un collaudo di integrazione usare la prova locale sopra.
