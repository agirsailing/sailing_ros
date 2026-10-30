# Installazione, aggiornamento e avvio del Raspberry

_Aggiornato al giorno: 30/10/2026_

[English](README_ENG.md) · [Indice repository](../README.md)

Gli script sono suddivisi per responsabilità. Per un Raspberry nuovo seguire
la [procedura completa via SSH](../guides/italiano/settaggio_raspberry.md), che
distingue i file da copiare e i comandi sul PC, sull'host Pi e nel container.
Non eseguire tutte le righe di questa pagina come una singola procedura.

## Punti di ingresso

| Script | Esecuzione sull'host Pi | Effetto |
|---|---|---|
| [steps/repository.sh](steps/repository.sh) | `bash /home/boat/repository.sh` sulla copia privata | Bootstrap senza argomenti: recupera la repository e crea la configurazione locale se assente |
| [complete_setup.sh](complete_setup.sh) | `bash complete_setup.sh` da utente boat | Configura host/hardware/Docker; repository full, pulizia e build completa; lascia il runtime fermo |
| [quick_setup.sh](quick_setup.sh) | `bash quick_setup.sh` oppure `bash quick_setup.sh --clean` | Aggiorna repository e immagine, compila; lascia il runtime fermo |
| [run.sh](run.sh) | `bash run.sh` | Aspetta la rete, avvia container e sistema live |
| [autostart_setup.sh](autostart_setup.sh) | `sudo bash autostart_setup.sh` | Installa, abilita **e avvia subito** `agir_regatta.service` |
| [network/install_wifi_guardian.sh](network/install_wifi_guardian.sh) | Installazione opzionale separata | Installa un controllo del profilo Wi-Fi al boot |

Gli script principali si lanciano da questa directory. Complete/quick non
installano l'autostart: farlo manualmente dopo le prove. Non usare `sudo` per
complete/quick/run; i singoli passi chiedono i privilegi quando necessari.

## Configurazione locale

[config.example.sh](config.example.sh) documenta le variabili; `config.local.sh`
è privato e ignorato da Git. Default: utente `boat`, home `/home/boat`, repository
`/home/boat/2025_SOFTWARE/sailing_ros`, branch `main`. Impostare `AGIR_BRANCH`
consapevolmente; quick aggiorna il checkout corrente e non è uno switch di branch.
`AGIR_TARGET_IP` cambia la destinazione del ping di attesa rete (default `8.8.8.8`).
Un router raggiungibile può essere più adatto quando manca Internet.

Git e MQTT hanno credenziali diverse. `repository.sh` riusa l'origin/helper Git
disponibile, oppure applica la coppia di credenziali configurata esplicitamente.
Non chiede username/token nel terminale e disabilita le finestre di autenticazione.
Se le credenziali HTTPS mancano, si ferma: compilare `GIT_USER` e `GIT_TOKEN`
nella copia privata di `repository.sh`, oppure `AGIR_GIT_USER` e `AGIR_GIT_TOKEN`
in `config.local.sh`. Il rifiuto dell'autenticazione interrompe lo script con
**«Errore nel token.»**, senza attribuirlo necessariamente alla scadenza.
Gli altri errori Git/rete hanno un messaggio distinto. Vale per bootstrap, `full`
e `update`; anche quick permette di sostituire le credenziali dal file locale.
Gli origin SSH già configurati usano le chiavi disponibili senza prompt.
Un token può trovarsi nell'URL di origin: non condividere l'output di remote/config.
Non committare copie compilate con segreti.

## Repository full e update

`full` allinea i file tracciati al branch remoto con reset: prima salvare altrove
eventuali modifiche necessarie. `update` usa pull con rebase/autostash. Entrambi
impostano `core.fileMode=false`; le modifiche del bit eseguibile non sporcano lo
status. Il workspace riceve `chmod -R 777`, comportamento attuale degli script.
`.gitattributes` gestisce i fine riga: è una questione distinta dai permessi.
La conversione `sed -i 's/\r$//'` serve solo se la copia bootstrap ha CRLF.

Quick ricostruisce l'immagine con cache; forza una build workspace pulita se
l'immagine cambia o con `--clean`, altrimenti incrementale. Dopo un cambiamento
agli script di setup, verificare il checkout prima di lanciarli: le funzioni
vengono caricate all'inizio, prima dell'aggiornamento Git interno.

## Moduli e hardware

| File | Responsabilità |
|---|---|
| [lib/common.sh](lib/common.sh) | Configurazione condivisa, controlli e caricamento dei passi |
| [steps/host.sh](steps/host.sh) | Preparazione host |
| [steps/hardware.sh](steps/hardware.sh) | I2C, UART, regole udev e permessi dispositivi |
| [steps/docker.sh](steps/docker.sh) | Installazione/configurazione Docker |
| [steps/repository.sh](steps/repository.sh) | Bootstrap, full/update e permessi workspace |
| [steps/workspace.sh](steps/workspace.sh) | Pulizia e compilazione nel container |
| [steps/runtime.sh](steps/runtime.sh) | Arresto, container e collegamento di avvio |

Udev assegna `/dev/ultrasonic_left` alla porta USB `1-1.4:1.0`,
`/dev/ultrasonic_right` a `1-1.3:1.0`, `/dev/gps` a `1-1.2:1.0`.
Cambiare presa/hub può cambiare questi percorsi. La BNO085 usa `/dev/ttyAMA0`:
il passo hardware abilita UART e rimuove la console seriale, richiedendo riavvio.

## Avvio e arresto

Run aspetta indefinitamente il ping prima di avviare ROS. Non interpreta questo
controllo come verifica di credenziali MQTT. Chiudere SSH non garantisce che il
processo lanciato nel container termini. Per fermare, prima chiudere la
registrazione; poi fermare il servizio se attivo e il container:

```bash
sudo systemctl stop agir_regatta.service
cd /home/boat/2025_SOFTWARE/sailing_ros
docker compose -f Docker/raspi_container/compose.yaml stop
```

Il primo comando serve solo se il servizio è installato. Per tornare a gestione
manuale permanente usare `sudo systemctl disable --now agir_regatta.service`.
Log autostart: `journalctl -u agir_regatta.service -b`.
