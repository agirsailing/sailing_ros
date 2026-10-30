# Configurazione e aggiornamento del Raspberry Pi

_Aggiornato al giorno: 30/10/2026_

[English](../inglese/raspberry_setup.md) · [Guide](../README.md)

Questa guida distingue due casi:

1. **Raspberry appena flashato:** installazione e configurazione iniziale del sistema di bordo.
2. **Raspberry già configurato:** aggiornamento del codice e ricompilazione.

L'**autostart**, cioè l'avvio automatico di ROS all'accensione, si abilita separatamente nella sezione finale, dopo aver provato il sistema manualmente. Tutta la procedura si svolge tramite SSH: non occorrono schermo, tastiera o una sessione desktop aperta sul Raspberry.

## Prima di iniziare

Sul PC devono essere già installati i [software necessari](software_necessari.md) e deve essere stata clonata la repository, come indicato nel [README delle guide](../README.md).

I comandi usano l'utente `boat`, il nome host `boat.local` e la repository sul Raspberry in `/home/boat/2025_SOFTWARE/sailing_ros`. Gli script scaricano il codice dal branch `main` su GitHub: prima di iniziare, assicurati che le modifiche da installare siano già presenti in quel branch.

Prepara la rete e l'accesso SSH seguendo la [guida alla connessione](connessione_raspberry.md). Il Raspberry deve avere accesso a Internet per scaricare codice, immagini e dipendenze. Esegui gli script sul Raspberry come utente `boat`, senza anteporre `sudo`: richiederanno i privilegi amministrativi quando necessari. Fa eccezione l'installer dell'autostart, per il quale il comando con `sudo` è riportato alla fine.

## Caso 1 — Raspberry appena flashato

### 1. Prepara il sistema operativo

Installa sulla scheda il sistema operativo a **64 bit per Raspberry Pi 4** indicato dal responsabile, usando Raspberry Pi Imager.

Durante la preparazione configura utente `boat`, hostname `boat`, password fornita dal responsabile, rete del team e accesso SSH. Accendi il Raspberry e verifica di riuscire a collegarti seguendo la [guida alla connessione](connessione_raspberry.md).

### 2. Prepara una copia privata di repository.sh sul PC

Copia [`DAY_BEFORE_REGATTA/steps/repository.sh`](../../DAY_BEFORE_REGATTA/steps/repository.sh) in una cartella del PC **esterna alla repository**. Per esempio, dalla radice `sailing_ros`:

**Windows — CMD:**

```cmd
copy "DAY_BEFORE_REGATTA\steps\repository.sh" "%USERPROFILE%\repository.sh"
```

**macOS — Bash:**

```bash
cp DAY_BEFORE_REGATTA/steps/repository.sh "$HOME/repository.sh"
```

Apri la copia con VS Code. Nella funzione `repository_configure()`, sostituisci queste due righe:

```bash
GIT_USER="${AGIR_GIT_USER:-${GIT_USER:-}}"
GIT_TOKEN="${AGIR_GIT_TOKEN:-${GIT_TOKEN:-}}"
```

con i valori forniti dal responsabile, al posto dei segnaposto dell'esempio:

```bash
GIT_USER='USERNAME_FORNITO_DAL_RESPONSABILE'
GIT_TOKEN='TOKEN_FORNITO_DAL_RESPONSABILE'
```

`GIT_TOKEN` è il token di accesso a GitHub. Mantieni invariati gli altri parametri, compreso il branch `main`. Salva il file con terminatori di riga **LF**: in VS Code puoi selezionarli dalla barra in basso.

Le credenziali vanno soltanto nella copia privata: non inserirle nel file originale della repository. Lo script non le chiede nel terminale. Se mancano, si ferma indicando quale file compilare; se l'autenticazione viene rifiutata, mostra **«Errore nel token.»**.

### 3. Trasferisci ed esegui repository.sh

Dal **terminale del PC**, copia il file nella home di `boat`.

**Windows — CMD:**

```cmd
scp "%USERPROFILE%\repository.sh" boat@boat.local:/home/boat/repository.sh
```

**macOS — Bash:**

```bash
scp "$HOME/repository.sh" boat@boat.local:/home/boat/repository.sh
```

Se hai scelto una cartella diversa per la copia privata, modifica il percorso locale. Collegati quindi dal PC:

```text
ssh boat@boat.local
```

Ora, nel **terminale SSH del Raspberry**, esegui lo script senza `sudo` e senza argomenti:

```bash
bash /home/boat/repository.sh
```

Lo script installa Git se necessario, scarica la repository e salva branch e percorsi in `DAY_BEFORE_REGATTA/config.local.sh`. Non avvia il setup completo: prima occorre copiare la configurazione MQTT.

Attendi il messaggio `Repository ready in /home/boat/2025_SOFTWARE/sailing_ros.` prima di proseguire.

Se hai salvato la copia con accapo Windows (CRLF) e Bash segnala errori contenenti `\r`, correggi il file sul Raspberry e rieseguilo:

```bash
sed -i 's/\r$//' /home/boat/repository.sh
bash /home/boat/repository.sh
```

Questo passaggio non serve se il file è già in formato LF. Le credenziali usate per il clone possono rimanere nell'URL di `origin`, nella configurazione Git locale: non condividere `.git/config` o l'output di `git remote -v` con il token visibile.

### 4. Copia la configurazione MQTT

Dopo il download della repository, copia dal PC il file con la configurazione della comunicazione con la web app:

| File | A cosa serve | Destinazione sul Raspberry |
|---|---|---|
| `mqtt_config.yaml` | Indirizzo del broker e credenziali MQTT dei gateway ROS. | `/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml` |

Richiedi al responsabile il file già compilato. Se devi prepararlo, parti da [`mqtt_config.example.yaml`](../../ros2_ws/src/communication_web/config/mqtt_config.example.yaml) e compila entrambi i blocchi dei gateway. Usa il nome host e la porta TCP/TLS del broker; l'URL `wss://` usato dal browser non va inserito nel campo host. Le credenziali MQTT sono diverse dal token GitHub.

Apri **un secondo terminale sul PC**, nella radice `sailing_ros`, lasciando aperta la sessione SSH. Con il file nella cartella locale `ros2_ws/src/communication_web/config/`, esegui lo stesso comando su Windows e macOS:

```text
scp ros2_ws/src/communication_web/config/mqtt_config.yaml boat@boat.local:/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/src/communication_web/config/mqtt_config.yaml
```

### 5. Esegui il setup completo

Torna al **terminale SSH del Raspberry** ed esegui [`complete_setup.sh`](../../DAY_BEFORE_REGATTA/complete_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/complete_setup.sh
```

Lo script configura sistema, collegamenti hardware e Docker, aggiorna il codice dal branch scelto e compila il workspace ROS. È destinato alla prima installazione: riallinea i file tracciati al branch remoto, scartando eventuali modifiche locali, e ricrea i risultati della compilazione.

Configura anche i nomi stabili delle porte USB e la UART dell'IMU. Git viene impostato per ignorare i cambiamenti del bit eseguibile (`core.fileMode=false`); gli accapo dei file del repository sono gestiti da `.gitattributes`.

Attendi che lo script termini senza errori e mostri `SETUP FINISHED! The system is ready but STOPPED.`. Il sistema è compilato, ma ROS rimane fermo: l'autostart non viene installato.

### 6. Riavvia e prova manualmente

Dopo il completamento del setup, sul Raspberry esegui:

```bash
sudo reboot
```

La sessione SSH si chiude. Il riavvio applica le modifiche I2C/UART e i gruppi utente. Attendi che il Raspberry riparta, poi ricollegati **dal PC**:

```text
ssh boat@boat.local
```

Nel **terminale SSH del Raspberry**, verifica che siano disponibili le porte dei sensori collegati e il container:

```bash
ls -l /dev/ultrasonic_left /dev/ultrasonic_right /dev/gps /dev/ttyAMA0 /dev/i2c-1
docker compose version
docker ps -a --filter name=agir-ros-raspi
```

I nomi USB dipendono dalle porte fisiche assegnate: sinistro `1-1.4:1.0`, destro `1-1.3:1.0`, GPS `1-1.2:1.0`. L'IMU BNO085 usa invece la UART `/dev/ttyAMA0` sui GPIO14/15; il setup disabilita Bluetooth e console seriale per dedicarle questa porta. Se un dispositivo manca, controlla il collegamento prima di avviare i nodi.

Segui ora la [guida all'avvio del sistema ROS](avvio_sistema_ros.md), partendo dall'avvio manuale. Verifica i dati dei sensori e la comunicazione con la web app prima di abilitare l'autostart.

## Caso 2 — Aggiornamento di un Raspberry già configurato

Questa procedura aggiorna il codice da `main` su GitHub e ricompila il sistema. Le modifiche da distribuire devono quindi essere già presenti in quel branch.

Collegati **dal PC**:

```text
ssh boat@boat.local
```

Nel **terminale SSH del Raspberry**, esegui [`quick_setup.sh`](../../DAY_BEFORE_REGATTA/quick_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
bash DAY_BEFORE_REGATTA/quick_setup.sh
```

Lo script ferma il servizio ROS e il container, aggiorna il codice e ricompila. Attendi il completamento senza errori. Il file MQTT e le impostazioni locali già presenti vengono conservati: per un normale aggiornamento non occorre ricopiarli. Anche le credenziali Git salvate vengono riutilizzate; per sostituirle compila `AGIR_GIT_USER` e `AGIR_GIT_TOKEN` in `DAY_BEFORE_REGATTA/config.local.sh`.

Se sono cambiati i messaggi ROS oppure sono stati eliminati o rinominati pacchetti, usa `bash DAY_BEFORE_REGATTA/quick_setup.sh --clean` al posto del comando normale.

Al termine ROS resta fermo. Per ripartire, segui la [guida all'avvio](avvio_sistema_ros.md) in base alla presenza o meno dell'autostart.

## Abilitare l'autostart

Quando la prova manuale è riuscita, interrompila con `Ctrl+C`. Dal **terminale SSH del Raspberry**, esegui [`autostart_setup.sh`](../../DAY_BEFORE_REGATTA/autostart_setup.sh):

```bash
cd /home/boat/2025_SOFTWARE/sailing_ros
sudo bash DAY_BEFORE_REGATTA/autostart_setup.sh
```

Lo script ferma eventuali processi della prova manuale, installa il servizio **`agir_regatta.service`**, lo abilita per le accensioni successive e **avvia subito ROS**. Non viene eseguito da complete o quick e non richiede una sessione desktop.

Per disabilitare l'avvio automatico e fermare anche il container attuale:

```bash
sudo systemctl disable --now agir_regatta.service
docker stop agir-ros-raspi
```

Per approfondire il ruolo di ogni script, consulta il [README di DAY_BEFORE_REGATTA](../../DAY_BEFORE_REGATTA/README.md).
