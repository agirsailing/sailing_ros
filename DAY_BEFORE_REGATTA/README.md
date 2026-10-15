# Preparazione e utilizzo del Raspberry Agir

La cartella segue la stessa organizzazione del progetto Polimi: comandi principali brevi, configurazione condivisa e passaggi specializzati. I valori predefiniti sono Raspberry Pi 4 con sistema a 64 bit, utente `boat`, repository `/home/boat/2025_SOFTWARE/sailing_ros`, branch `main`, ROS Jazzy e container `agir-ros-raspi`.

**Prima configura e prova tutto manualmente. L'avvio automatico si installa soltanto quando esegui tu `autostart_setup.sh`.** Né il setup completo, né il quick, né `run.sh` chiamano quell'installatore.

## Struttura

```text
DAY_BEFORE_REGATTA/
├── complete_setup.sh
├── quick_setup.sh
├── run.sh
├── autostart_setup.sh
├── config.example.sh
├── config.local.sh          # facoltativo, privato e ignorato da Git
├── agir_regatta.service     # modello di riferimento per la configurazione predefinita
├── lib/common.sh
├── steps/
│   ├── host.sh
│   ├── hardware.sh
│   ├── docker.sh
│   ├── repository.sh
│   ├── workspace.sh
│   └── runtime.sh
├── network/
│   ├── agir_wifi_check.sh
│   └── install_wifi_guardian.sh
└── tests/test_setup.py
```

| Comando | Cosa fa |
| --- | --- |
| `complete_setup.sh` | Configura sistema, SSH, hardware e Docker; riallinea Git al branch remoto e compila tutto da zero. Lascia ROS fermo. |
| `quick_setup.sh` | Aggiorna Git con rebase/autostash, ricostruisce Docker usando la cache e compila ROS in modo incrementale quando possibile. Lascia ROS fermo. |
| `quick_setup.sh --clean` | Come il quick, ma richiede una compilazione ROS pulita. |
| `run.sh` | Avvia manualmente container e ROS in modalità `live`, mantenendo i log nel terminale. |
| `autostart_setup.sh` | Solo su tua esecuzione esplicita: installa, abilita al boot e avvia subito il servizio ROS. |
| `network/install_wifi_guardian.sh` | Installazione separata e facoltativa del controllo Wi-Fi al boot. |

Gli script in `steps/` contengono funzioni caricate dai comandi principali. `steps/repository.sh` è anche un comando autonomo, come nel progetto Polimi: `complete_setup.sh` lo esegue con l'argomento `full`, mentre `quick_setup.sh` usa `update`. Le funzioni necessarie a proseguire il setup sono caricate prima che Git aggiorni i file, anche quando l'operazione Git viene eseguita in un processo Bash separato.

| Comando | Operazione |
| --- | --- |
| `bash DAY_BEFORE_REGATTA/steps/repository.sh` | Primo download; se la repository esiste, aggiornamento `--ff-only`. Crea la configurazione locale se manca. |
| `bash DAY_BEFORE_REGATTA/steps/repository.sh full` | Clona oppure riallinea al remoto con `reset --hard`, scartando le modifiche locali tracciate. |
| `bash DAY_BEFORE_REGATTA/steps/repository.sh update` | Richiede una repository esistente, aggiorna con `pull --rebase --autostash` e applica `chmod -R 777` a `ros2_ws`. |

Tutte le modalità impostano `core.fileMode=false`. Nessuna avvia Docker, compila ROS o abilita l'autostart. Puoi ancora copiare il solo `repository.sh` sul Raspberry per il primo download; Agir non supporta `--setup`, così puoi copiare MQTT prima di eseguire esplicitamente il setup completo.

## Procedura passo passo: Raspberry appena installato, solo SSH

Questa procedura arriva dal primo download ai test manuali e poi all'autostart. Il Raspberry funziona senza schermo e senza desktop: Wayland, X11 e login grafico non sono richiesti.

**Dove eseguire i comandi:** i blocchi **PC — PowerShell** vanno eseguiti sul computer Windows. Dopo `ssh boat@boat.local`, i blocchi **Raspberry — Bash via SSH** vanno eseguiti nella sessione remota. Per tornare al PC usa un'altra finestra PowerShell oppure esci da SSH con `exit`. Negli esempi sostituisci `boat.local` con l'IP del Raspberry se il nome non si risolve.

I soli file da copiare manualmente sono:

| File sul PC | Destinazione sul Raspberry |
| --- | --- |
| Copia privata di `DAY_BEFORE_REGATTA/steps/repository.sh` | `/home/boat/repository.sh` |
| `ros2_ws/src/communication_web/config/mqtt_config.yaml` compilato | `/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml` |

Il resto viene scaricato da Git. Il primo download crea già `config.local.sh`: non devi copiarlo o ricrearlo manualmente.

### 1. PC — Pubblica gli script aggiornati

Fai commit e push delle modifiche sul branch che scaricherai, normalmente `main`. Quel branch deve contenere gli script aggiornati descritti qui. Non includere token o configurazioni private nei commit.

### 2. PC — Prepara la scheda del Raspberry

Durante la preparazione dell'immagine imposta:

- Sistema a **64 bit** compatibile con il setup per Raspberry Pi 4.
- Utente **`boat`**, con password o chiave SSH configurata.
- Hostname **`boat`**.
- **SSH abilitato** fin dal primo avvio.
- Wi-Fi configurato, oppure collegamento Ethernet.

Accendi il Raspberry e attendi che si colleghi alla rete. Per scaricare codice, pacchetti e immagini Docker serve accesso a Internet durante il setup.

### 3. PC — Prepara e trasferisci repository.sh

**PC — PowerShell:** crea una copia privata fuori dalla repository e aprila.

```powershell
Copy-Item "C:\Users\ettor\Desktop\Agir_Sailing_Team\sailing_ros\DAY_BEFORE_REGATTA\steps\repository.sh" "$env:USERPROFILE\repository.sh"
notepad "$env:USERPROFILE\repository.sh"
```

Nella funzione `repository_configure()` della **copia privata**, sostituisci le due assegnazioni di credenziali con i tuoi valori. Questo è contenuto del file, non un comando da eseguire nel terminale:

```bash
GIT_USER="IL_TUO_USERNAME_GITHUB"
GIT_TOKEN="IL_TUO_TOKEN_GITHUB"
```

Lascia il branch `main` se hai pubblicato lì; altrimenti modifica anche il valore predefinito di `BRANCH`. Salva preferibilmente con accapo **LF**. Non inserire il token nella copia originale tracciata da Git.

**PC — PowerShell:** trasferisci la copia e apri la connessione SSH.

```powershell
scp "$env:USERPROFILE\repository.sh" boat@boat.local:/home/boat/repository.sh
ssh boat@boat.local
```

### 4. Raspberry via SSH — Scarica la repository

**Accapo: il comando `sed` non è obbligatorio.** Se la copia è già salvata con accapo LF, salta questo blocco. Se è stata salvata con accapo Windows CRLF, oppure Bash segnala errori come `$'\r': command not found`, correggi la copia trasferita prima di eseguirla.

**Raspberry — Bash via SSH, solo se occorre convertire CRLF in LF:**

```bash
sed -i 's/\r$//' /home/boat/repository.sh
```

Il comando rimuove il carattere CR alla fine delle righe; su un file già LF non cambia nulla. `.gitattributes` gestisce gli accapo dei file della repository, ma un editor può modificare gli accapo della copia privata trasferita con `scp`.

**Raspberry — Bash via SSH:** esegui il primo download **senza `sudo` e senza argomenti**.

```bash
bash /home/boat/repository.sh
```

Installa Git se manca, clona la repository in `/home/boat/2025_SOFTWARE/sailing_ros` e crea `DAY_BEFORE_REGATTA/config.local.sh` con utente, percorsi e branch. Non esegue Docker, compilazione o autostart. Il token usato per clonare resta nell'origin Git locale, ma non viene ricopiato in `config.local.sh`.

Se la repository esiste già, questo comando aggiorna con `--ff-only`, senza reset. Non devi chiamare manualmente `full` o `update` in questa procedura: sono richiamati dai rispettivi setup.

### 5. PC — Copia mqtt_config.yaml

Prepara il file privato `ros2_ws/src/communication_web/config/mqtt_config.yaml` usando il modello `mqtt_config.example.yaml` nella stessa cartella. Compila entrambe le sezioni: `telemetry_gateway_node` e `command_gateway_node`.

**PC — Un secondo PowerShell, fuori dalla sessione SSH:**

```powershell
scp "C:\Users\ettor\Desktop\Agir_Sailing_Team\sailing_ros\ros2_ws\src\communication_web\config\mqtt_config.yaml" boat@boat.local:/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml
```

Il file MQTT è ignorato da Git; il riallineamento del setup conserva questo file locale finché resta non tracciato. Con gli script attuali non c'è un `git clean` che lo rimuova.

### 6. Raspberry via SSH — Esegui il setup completo e riavvia

**Raspberry — Bash via SSH:**

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/complete_setup.sh
```

Non anteporre `sudo`: lo script lo usa internamente quando serve. Configura sistema, hardware, regole delle porte e Docker, poi compila ROS. Il passaggio Git `full` riallinea i file tracciati al remoto, scartando eventuali modifiche locali a quei file.

**Solo dopo il completamento riuscito**, riavvia per applicare anche la configurazione I2C e l'appartenenza al gruppo Docker.

**Raspberry — Bash via SSH:**

```bash
sudo reboot
```

La connessione SSH si chiude. ROS non è ancora configurato per partire automaticamente.

### 7. Ricollegati e verifica i dispositivi

Attendi il riavvio, poi collegati di nuovo.

**PC — PowerShell:**

```powershell
ssh boat@boat.local
```

Collega i sensori alle porte USB previste: ultrasuoni sinistro `1.4`, destro `1.3`, GPS `1.2`. Sono identificativi del percorso USB usato dalle regole udev, non la numerazione dei dispositivi `ttyUSB`.

**Raspberry — Bash via SSH:**

```bash
ls -l /dev/ultrasonic_left /dev/ultrasonic_right /dev/gps
```

Con tutti e tre i dispositivi collegati alle porte corrette devono comparire i tre alias. Se ne manca uno, controlla collegamento e porta prima di procedere con il test del relativo sensore.

### 8. Raspberry via SSH e GUI sul PC — Prove manuali

`run.sh` aspetta una risposta al ping di `8.8.8.8`. Se userai una rete senza Internet, imposta prima un indirizzo raggiungibile, per esempio quello del router. Questo modifica soltanto il controllo iniziale: MQTT richiede comunque che il broker sia raggiungibile.

**Raspberry — Bash via SSH, solo per cambiare il controllo di rete:**

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
nano DAY_BEFORE_REGATTA/config.local.sh
```

Aggiungi nel file questa assegnazione, sostituendo l'indirizzo d'esempio con quello effettivo del router:

```bash
export AGIR_TARGET_IP=192.168.1.1
```

**Raspberry — Bash via SSH:** avvia manualmente ROS.

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/run.sh
```

Lascia aperta questa sessione SSH per seguire i log. Verifica che:

- I sensori producano dati e non compaiano errori ripetuti di accesso ai dispositivi.
- La GUI aperta sul **PC** riceva la telemetria.
- I comandi inviati dalla GUI arrivino al Raspberry.
- Avvio e arresto della registrazione funzionino e venga prodotto un file di registrazione. La registrazione **non parte automaticamente** insieme a ROS.

Per controllare direttamente ROS, apri un'altra connessione mentre quella principale resta attiva.

**PC — Un secondo PowerShell:**

```powershell
ssh boat@boat.local
```

**Raspberry — Nella seconda sessione SSH:** entra nel container.

```bash
docker exec -it agir-ros-raspi bash
```

**Container sul Raspberry — Nello stesso terminale, dopo il comando precedente:**

```bash
source /opt/ros/jazzy/setup.bash
source /home/ros/ros2_ws/install/setup.bash
ros2 node list
ros2 topic list
ros2 topic echo /gps/data --once
```

L'ultimo comando attende un messaggio GPS; puoi interromperlo con `Ctrl+C` se non arrivano dati. Usa `exit` per uscire dalla shell del container e tornare alla shell SSH.

Per terminare la prova, nella **prima sessione SSH** premi `Ctrl+C` sul comando `run.sh`, poi ferma il container.

**Raspberry — Bash via SSH:**

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
docker compose -f Docker/raspi_container/compose.yaml stop
```

### 9. Raspberry via SSH — Abilita l'autostart quando i test funzionano

**Raspberry — Bash via SSH, soltanto quando decidi tu:**

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
sudo bash DAY_BEFORE_REGATTA/autostart_setup.sh
```

Questo comando abilita il servizio al boot e **avvia subito ROS**. Controlla stato e log.

**Raspberry — Bash via SSH:**

```bash
sudo systemctl status agir_regatta.service --no-pager
sudo journalctl -u agir_regatta.service -f
```

Qui `Ctrl+C` interrompe soltanto la visualizzazione dei log, non il servizio ROS.

### 10. Riavvia e verifica l'avvio automatico

**Raspberry — Bash via SSH:**

```bash
sudo reboot
```

ROS deve partire al boot anche senza nessuno collegato via SSH e senza login desktop. Attendi il riavvio, poi ricollegati per verificare.

**PC — PowerShell:**

```powershell
ssh boat@boat.local
```

**Raspberry — Bash via SSH:**

```bash
sudo systemctl status agir_regatta.service --no-pager
sudo journalctl -u agir_regatta.service -b --no-pager -n 100
```

Controlla nuovamente la telemetria dalla GUI sul PC: il solo stato `active` non basta a confermare che ROS sia già operativo, perché lo script potrebbe essere ancora in attesa della rete.

Se vuoi tornare all'avvio manuale, disabilita l'autostart e ferma il servizio.

**Raspberry — Bash via SSH, solo per disabilitare l'autostart:**

```bash
sudo systemctl disable --now agir_regatta.service
```

## Riferimento: configurazione condivisa

I valori predefiniti funzionano senza creare altri file. Per personalizzare utente, percorsi, branch o credenziali, dalla radice della repository:

```bash
cp DAY_BEFORE_REGATTA/config.example.sh DAY_BEFORE_REGATTA/config.local.sh
nano DAY_BEFORE_REGATTA/config.local.sh
```

`config.example.sh` è soltanto un modello, non uno script da eseguire. `config.local.sh` è letto dai comandi principali e ignorato da Git. Il bootstrap `repository.sh` lo crea se manca; i setup non lo sovrascrivono. Le assegnazioni nel file locale hanno precedenza sulle variabili d'ambiente. Se hai già eseguito il bootstrap, non ricopiare il modello sopra la tua configurazione.

I parametri disponibili sono `AGIR_USER`, `AGIR_USER_HOME`, `AGIR_REPO_DIR`, `AGIR_BRANCH`, `AGIR_GIT_USER`, `AGIR_GIT_TOKEN` e `AGIR_TARGET_IP`. Imposta utente e home in modo coerente. Docker non dipende da un UID desktop fisso né da socket grafici nella sessione dell'utente.

### Autenticazione Git

Il refactoring conserva la logica degli script presenti nella repository: nel setup completo, senza credenziali esplicite viene riutilizzato l'`origin` esistente e Git gestisce l'autenticazione. Un'eventuale coppia `AGIR_GIT_USER`/`AGIR_GIT_TOKEN` configura o sostituisce l'URL HTTPS. Entrambi i valori sono richiesti per sostituirla. Sono ancora supportate le variabili d'ambiente `GIT_USER`/`GIT_TOKEN` quando le corrispondenti variabili `AGIR_` non sono impostate.

Il quick usa sempre l'`origin` già configurato. Su una nuova clonazione l'URL predefinito è HTTPS. Git può usare un gestore di credenziali configurato o chiedere le credenziali se mancano. L'URL autenticato conserva il token in chiaro nella `.git/config` locale, fuori dai commit: non pubblicare credenziali nei file tracciati.

## Riferimento: setup completo

Prima fai commit e push degli script sul branch che il Raspberry scaricherà. Sul Raspberry, come utente `boat` e senza anteporre `sudo`:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/complete_setup.sh
```

Il setup ferma prima un eventuale servizio regata e poi il container, configura il sistema, aggiorna Git, pulisce `build/install/log`, ricostruisce l'immagine senza cache e compila ROS. Al termine lascia container e ROS fermi. I singoli passaggi amministrativi usano `sudo` quando serve.

**Il setup completo scarta le modifiche locali ai file tracciati**, riallineando la repository a `origin/main` o al branch configurato. Per gli aggiornamenti ordinari usa il quick.

Su un Raspberry senza repository, usa prima il solo `steps/repository.sh` come indicato sopra: in questo modo puoi consegnare MQTT prima della compilazione. `complete_setup.sh` richiede comunque `lib/` e `steps/` accanto a sé, che a quel punto sono già stati scaricati da Git.

Prepara inoltre il file privato `ros2_ws/src/communication_web/config/mqtt_config.yaml` secondo il relativo modello, prima di avviare ROS.

Riavvia il Raspberry per applicare la configurazione I2C e l'appartenenza al gruppo Docker. Il setup non abilita l'avvio automatico di ROS.

## Riferimento: prova manuale

Dopo il setup e il riavvio:

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/run.sh
```

`run.sh` attende una risposta al ping di `8.8.8.8`, avvia il container e lancia `ros2_ws/scripts/run.sh live`. Puoi scegliere un altro indirizzo con `AGIR_TARGET_IP` in `config.local.sh`, per esempio il router locale quando non hai Internet. Se l'indirizzo non risponde, l'attesa continua.

Il comando funziona tramite SSH senza sessione grafica. Sensori, elaborazione,
MQTT e registrazione girano sul Raspberry; la GUI web si apre sul PC. Eventuali
strumenti grafici come RViz/rqt vanno usati sul PC con la relativa configurazione
Docker per PC. Non occorre aprirli sul Raspberry per far funzionare il sistema live.

Verifica sensori, comunicazione con la GUI e registrazione. L'avvio di ROS non avvia automaticamente una registrazione: questa parte su comando.

Per terminare la prova, interrompi il comando con `Ctrl+C` e ferma il container:

```bash
docker compose -f Docker/raspi_container/compose.yaml stop
```

Se avevi già installato il servizio regata, prima delle prove manuali fermalo con `sudo systemctl stop agir_regatta.service`: evita di avviare ROS contemporaneamente dal servizio e dal terminale. Se non vuoi che riparta al riavvio, usa `sudo systemctl disable --now agir_regatta.service`. Il setup conserva l'eventuale abilitazione già esistente.

## Riferimento: avvio automatico

Quando tutto funziona manualmente, esegui **tu** questo comando dalla repository:

```bash
sudo bash DAY_BEFORE_REGATTA/autostart_setup.sh
```

Questo comando ferma un eventuale servizio/container già attivo, genera il servizio usando utente e percorso della configurazione comune, lo abilita al boot e lo avvia subito. Il servizio esegue `run.sh` direttamente dalla repository, dove trova anche la configurazione e i moduli. Il file `agir_regatta.service` è un riferimento con i valori predefiniti; l'installatore genera quello effettivo.

Il servizio è di sistema: al boot non richiede né una connessione SSH né un login
desktop. Rimangono necessari Docker, accesso ai dispositivi e la rete; il controllo
ping di `run.sh` resta attivo anche nell'avvio automatico. Dopo un riavvio puoi
verificare lo stato collegandoti via SSH ed eseguendo
`sudo systemctl status agir_regatta.service --no-pager`.

Nessun altro script richiama `autostart_setup.sh`. Il setup completo e il quick non installano, abilitano o avviano il servizio regata. Mantengono solo la compatibilità con un vecchio launcher già installato in `/usr/local/bin/agir_regatta_start.sh`, aggiornandolo per richiamare `run.sh`.

Comandi utili dopo l'installazione:

```bash
sudo journalctl -u agir_regatta.service -f
sudo systemctl stop agir_regatta.service
sudo systemctl start agir_regatta.service
sudo systemctl disable --now agir_regatta.service
```

## Aggiornamenti successivi

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/quick_setup.sh
# Oppure, per richiedere una compilazione pulita:
bash DAY_BEFORE_REGATTA/quick_setup.sh --clean
```

Il quick conserva il `pull --rebase --autostash`. Controlla l'immagine registrata dall'ultima compilazione riuscita in `ros2_ws/build/.agir_image_id`: se cambia o il riferimento manca, usa una compilazione pulita. Un errore di compilazione non aggiorna quel riferimento.

Entrambi i setup lasciano ROS fermo anche dopo una compilazione fallita. Dopo un aggiornamento riuscito riparti con `run.sh` oppure, se hai già scelto di installarlo, con `sudo systemctl start agir_regatta.service`. Non riavviare il Raspberry né avviare il servizio durante l'aggiornamento.

## Wi-Fi: configurazione separata

Il controllo Wi-Fi rimane facoltativo e non viene installato dai setup. Compila SSID, password e nome del profilo in una copia locale di `network/agir_wifi_check.sh`, senza pubblicare le credenziali. Poi esegui:

```bash
sudo bash DAY_BEFORE_REGATTA/network/install_wifi_guardian.sh
```

L'installatore cerca il controllo Wi-Fi nella propria cartella, quindi funziona anche se lo esegui da un'altra directory. Installa, abilita e avvia il servizio `agir_wifi_guardian.service`. Richiede NetworkManager e lavora una volta al boot; non è un monitor continuo. È indipendente dal servizio ROS.

## Hardware e permessi

Il setup completo configura I2C, GPIO e le regole USB in `/etc/udev/rules.d/99-boat-serial.rules`:

| Sensore | Porta fisica / interfaccia USB | Nome stabile |
| --- | --- | --- |
| Ultrasuoni sinistro | `1-1.4:1.0` | `/dev/ultrasonic_left` |
| Ultrasuoni destro | `1-1.3:1.0` | `/dev/ultrasonic_right` |
| GPS | `1-1.2:1.0` | `/dev/gps` |

Mantieni i cavi nelle stesse porte. I nomi sono usati nel file dei parametri dei sensori e risultano visibili nel container attraverso il montaggio di `/dev`. Se manca un sensore il setup avvisa e prosegue. Bus e canali I2C, indirizzi e linea GPIO restano da verificare sul cablaggio reale.

Sono conservati i permessi hardware `0666` e i permessi workspace `777`. L'impostazione Git `core.fileMode=false` viene applicata sia nel primo download sia nelle modalità `full` e `update`. Gli accapo sono gestiti dal `.gitattributes` della repository.

## Componenti e verifiche

`host.sh` gestisce controlli Pi 4, hostname, pacchetti e SSH; `hardware.sh` gestisce I2C e udev; `docker.sh` gestisce Docker/Compose; `repository.sh` gestisce Git; `workspace.sh` gestisce compilazione e riferimento dell'immagine; `runtime.sh` gestisce arresto e compatibilità con il vecchio launcher.

Per eseguire i test su un PC con Python 3 e Bash, anche Git for Windows:

```bash
python DAY_BEFORE_REGATTA/tests/test_setup.py
```

I test usano copie temporanee e comandi amministrativi simulati. Non sostituiscono la prova sul Raspberry: restano da verificare sensori, rete, avvio reale di Docker e ROS e funzionamento dopo il riavvio. Nessuna sessione desktop è necessaria.
