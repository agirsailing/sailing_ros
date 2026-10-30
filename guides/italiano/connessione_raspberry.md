# Connessione al Raspberry Pi

_Aggiornato al giorno: 30/10/2026_

[English](../inglese/raspberry_connection.md)

Questa guida spiega come accedere al Raspberry Pi tramite SSH e copiare file tra il computer e il dispositivo. Per configurare il Raspberry, avviare ROS o verificare il sistema, consulta [Settaggio del Raspberry Pi](settaggio_raspberry.md). Un Raspberry appena flashato contiene il sistema operativo, ma non ancora la repository e il software di bordo.

## Prima di collegarti

Sul computer deve essere disponibile il **client SSH**: se manca, segui la [guida ai software necessari](software_necessari.md#1-ssh-da-terminale). Anche sul Raspberry deve essere abilitato l'accesso SSH.

1. Assicurati che il Raspberry sia acceso.
2. Collega PC e Raspberry alla stessa rete Wi-Fi o hotspot. Richiedi nome e password della rete al team.
3. Se `boat.local` non viene risolto, usa l’indirizzo IP assegnato al Raspberry dal router. Verifica che l’hotspot consenta la comunicazione tra i dispositivi.

## Accesso tramite SSH

Apri **CMD su Windows** oppure **Terminale con Bash su macOS** ed esegui:

```text
ssh boat@boat.local
```

Al primo collegamento SSH può chiederti di confermare l'identità del dispositivo: verifica l'impronta della chiave con il responsabile e rispondi `yes`.

Quando viene richiesta la password dell'utente `boat`, inserisci quella fornita dal tuo responsabile. È distinta dalla password Wi-Fi. Durante la digitazione non compaiono caratteri: è normale.

Dopo l'accesso, i comandi digitati in quella sessione vengono eseguiti sul Raspberry. Per uscire e tornare al computer usa `exit`.

### Avviso di chiave del dispositivo cambiata

Se prima della richiesta della password compare un messaggio simile a questo:

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
Host key verification failed.
```

la chiave del dispositivo è diversa da quella salvata sul computer. Può succedere dopo aver riflashato il Raspberry. Se il responsabile conferma il cambio della chiave, rimuovi il vecchio riferimento dal terminale del computer:

```text
ssh-keygen -R boat.local
```

Il comando rimuove la chiave memorizzata per `boat.local` dal file `known_hosts`, come descritto nel [manuale OpenSSH](https://man.openbsd.org/ssh-keygen#R). Ripeti quindi la connessione e conferma la nuova chiave verificata:

```text
ssh boat@boat.local
```

Se il cambio non è atteso, chiariscilo con il responsabile prima di rimuovere la chiave salvata.

## Copiare file e cartelle

Esegui questi comandi **dal terminale del tuo computer**, non dalla sessione SSH aperta sul Raspberry: apri un secondo terminale oppure esci con `exit`.

`scp` copia i dati attraverso SSH e può chiedere la stessa password dell'utente `boat`. L'opzione `-r` include una cartella e tutto il suo contenuto; per un singolo file si può omettere. Riferimento: [manuale di scp](https://man.openbsd.org/scp).

### Dal computer al Raspberry

Forma generale, sostituendo i percorsi e il nome utente:

```text
scp -r "pc_path_file" username@boat.local:path_raspberry
```

Esempio da CMD su Windows:

```cmd
scp -r "C:\Users\ettor\Desktop\Temp\script.sh" boat@boat.local:/home/boat
```

Il comando copia `script.sh` dal computer alla cartella `/home/boat` del Raspberry. **Copia il file, senza eseguirlo.**

### Dal Raspberry al computer

Per esempio, per copiare sul PC la cartella delle rosbag di un Raspberry già configurato con i percorsi del progetto:

```cmd
scp -r boat@boat.local:/home/boat/2025_SOFTWARE/sailing_ros/ros2_ws/rosbags/raw_recordings "C:\Users\ettor\Desktop\Temp"
```

Il comando copia `raw_recordings` e il suo contenuto in `C:\Users\ettor\Desktop\Temp\raw_recordings`, lasciando gli originali sul Raspberry. Copia registrazioni già concluse.

Negli esempi le cartelle di destinazione devono esistere. Sostituisci i percorsi con quelli del tuo computer; su macOS usa un percorso locale come `/Users/tuo_utente/Desktop/Temp`. Il percorso remoto delle rosbag vale per l'installazione del progetto indicata e non esiste su un Raspberry appena flashato.

Per configurare o avviare il sistema ROS, prosegui con [Settaggio del Raspberry Pi](settaggio_raspberry.md).
