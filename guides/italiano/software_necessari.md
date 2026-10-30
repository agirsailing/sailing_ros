# Software necessari

_Aggiornato al giorno: 30/10/2026_

[English](../inglese/software_necessary.md)

Questa guida elenca i software da installare sul proprio computer per lavorare alla repository. Le istruzioni sono rivolte a **Windows** e **macOS**.

Tutti i membri devono avere a disposizione **SSH da terminale, Git, GitHub Desktop, Docker Desktop e Visual Studio Code con le estensioni elencate sotto**. I server X e i programmi aggiuntivi per le connessioni remote sono opzionali.

## Software obbligatori

### 1. SSH da terminale

SSH permette di collegarsi al Raspberry Pi ed eseguire comandi da remoto. Sul computer serve il **client OpenSSH**. Se è già disponibile, non occorre reinstallarlo.

#### Windows: Prompt dei comandi (CMD)

Apri il **Prompt dei comandi**, cercando `cmd` nel menu Start, ed esegui:

```cmd
ssh -V
```

Se compare la versione di OpenSSH, il client è disponibile. Se il comando non viene riconosciuto, apri le **Funzionalità facoltative** di Windows e aggiungi **Client OpenSSH**, seguendo la [guida ufficiale Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse). Per collegarti al Raspberry basta il client; non serve installare OpenSSH Server sul PC.

Dopo l'installazione riapri CMD e ripeti `ssh -V`. Per le connessioni al Raspberry usa CMD.

#### macOS: Terminale con Bash

Apri l'app **Terminale** e avvia Bash:

```bash
/bin/bash
```

Quindi verifica che SSH sia disponibile:

```bash
ssh -V
```

Il client SSH è già disponibile su macOS. Per l'uso delle connessioni remote consulta la [guida ufficiale Apple](https://support.apple.com/it-it/guide/terminal/trml1018/mac). Avviare Bash in questo modo vale per la sessione corrente e non richiede di cambiare la shell predefinita del Mac.

### 2. Git e GitHub Desktop

Installa **entrambi**:

- **Git** gestisce le versioni del codice e permette di usare comandi come `git clone` dal terminale.
- **GitHub Desktop** offre un'interfaccia grafica per lavorare con repository, branch, commit e sincronizzazione con GitHub.

| Software | Windows | macOS |
|---|---|---|
| Git | [Download e installazione](https://git-scm.com/install/windows) | [Guida ufficiale all'installazione](https://git-scm.com/install/mac) |
| GitHub Desktop | [Download](https://desktop.github.com/download/) | [Download](https://desktop.github.com/download/) |

Su macOS puoi installare Git tramite gli strumenti da riga di comando di Xcode, come indicato nella guida ufficiale:

```bash
xcode-select --install
```

Al termine dell'installazione, riapri CMD o Terminale e verifica:

```text
git --version
```

Apri quindi GitHub Desktop e accedi con il tuo account GitHub.

### 3. Docker Desktop

Docker Desktop permette di eseguire l'ambiente ROS 2 del progetto in un container, con le dipendenze necessarie allo sviluppo.

| Sistema | Download e guida di installazione |
|---|---|
| Windows | [Docker Desktop per Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| macOS | [Docker Desktop per Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |

Su Windows segui anche i requisiti e le istruzioni per **WSL 2** riportati nella guida Docker. Su Mac scegli il download adatto al processore: **Apple silicon** oppure **Intel**.

Dopo l'installazione apri Docker Desktop e attendi che il motore Docker sia avviato. La configurazione dell'ambiente del progetto è descritta nella [guida al settaggio del PC](settaggio_pc.md).

### 4. Visual Studio Code e relative estensioni

Installa [Visual Studio Code dal sito ufficiale](https://code.visualstudio.com/download). Lo useremo per modificare il codice, eseguire il debug e lavorare all'interno del container ROS.

Apri la sezione **Estensioni** di VS Code e installa tutte le estensioni della tabella. I link portano alle rispettive pagine del Visual Studio Marketplace.

| Estensione | Scopo | Installazione |
|---|---|---|
| Git Extension Pack | Strumenti per la cronologia e la gestione dei repository Git. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=donjayamanne.git-extension-pack) |
| Docker Extension Pack | Gestione di container, immagini e file Docker. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=formulahendry.docker-extension-pack) |
| Remote Development | Sviluppo nei container e collegamento a macchine remote tramite SSH. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) |
| C/C++ Extension Pack | Completamento del codice, debug e strumenti per C/C++. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools-extension-pack) |
| Python Extension Pack | Strumenti per scrivere, controllare e fare debug del codice Python. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=donjayamanne.python-extension-pack) |
| ROS | Supporto ai file ROS, ai messaggi e ai modelli URDF/Xacro. | [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-iot.vscode-ros) |

Il pacchetto **Remote Development** include **Dev Containers**, per lavorare nel container, e **Remote - SSH**, per collegare l'editor a una macchina remota.

## Software opzionali

### Server X

Un server X permette di visualizzare sul computer le finestre di applicazioni grafiche eseguite nel container, come `rviz2` e `rqt`.

| Sistema | Software | Download |
|---|---|---|
| Windows | VcXsrv | [Release ufficiali del progetto](https://github.com/marchaesen/vcxsrv/releases) |
| macOS | XQuartz | [Sito ufficiale](https://www.xquartz.org/) |

L'uso della grafica richiede anche la configurazione del collegamento tra container e server X. Per i collegamenti grafici definiti dal progetto, consulta il [README Docker](../../Docker/README.md).

### Strumenti per le connessioni remote

Questi programmi aggiungono un'interfaccia per salvare e gestire le connessioni SSH. Sono facoltativi: la connessione da terminale descritta sopra rimane il metodo di riferimento.

| Sistema | Software | Download |
|---|---|---|
| Windows | MobaXterm | [Sito ufficiale](https://mobaxterm.mobatek.net/download.html) |
| macOS | Termius | [Sito ufficiale](https://termius.com/download/macos) |

Durante l'esecuzione del software di bordo, usa una normale sessione SSH da terminale e chiudi le sessioni VS Code Remote - SSH collegate al Raspberry, per lasciare le risorse del dispositivo al sistema ROS.

[Torna alle guide](../README.md)
