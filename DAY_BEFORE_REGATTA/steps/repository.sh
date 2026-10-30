#!/usr/bin/env bash
# Standalone Git step: no arguments for bootstrap, full or update for setup.
# Functions may also be loaded by lib/common.sh without executing operations.

repository_validate_credentials() {
  # Accept placeholders left in older local copies as unset values.
  if [[ "$GIT_USER" == INSERT_* ]]; then GIT_USER=""; fi
  if [[ "$GIT_TOKEN" == INSERT_* ]]; then GIT_TOKEN=""; fi
  if [[ ( -n "$GIT_USER" && -z "$GIT_TOKEN" ) || ( -z "$GIT_USER" && -n "$GIT_TOKEN" ) ]]; then
    repository_missing_credentials
    exit 1
  fi
}

repository_missing_credentials() {
  echo "Credenziali Git mancanti o incomplete."
  echo "Compila GIT_USER e GIT_TOKEN nella copia privata di repository.sh, oppure AGIR_GIT_USER e AGIR_GIT_TOKEN in DAY_BEFORE_REGATTA/config.local.sh."
}

repository_git() {
  # Never prompt in the terminal, an askpass dialog or Git Credential Manager.
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
    GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh} -oBatchMode=yes -oStrictHostKeyChecking=yes" \
    git -c credential.interactive=false "$@"
}

repository_prepare_remote() {
  local saved credentials line has_user=0 has_password=0
  local -a context=()
  REPO_URL="https://github.com/${REPO_SLUG}.git"
  if [[ -d "$REPO_DIR/.git" ]]; then
    context=(-C "$REPO_DIR")
    if saved="$(git "${context[@]}" remote get-url origin 2>/dev/null)"; then
      REPO_URL="$saved"
    fi
  fi
  if [[ -n "$GIT_USER" ]]; then
    REPO_URL="https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git"
  elif [[ "$REPO_URL" == https://* || "$REPO_URL" == http://* ]]; then
    # Git resolves embedded credentials and configured helpers; keep the result private.
    credentials="$(printf 'url=%s\n\n' "$REPO_URL" |
      repository_git "${context[@]}" credential fill 2>/dev/null)" || {
        repository_missing_credentials
        return 1
      }
    while IFS= read -r line; do
      [[ "$line" != username=?* ]] || has_user=1
      [[ "$line" != password=?* ]] || has_password=1
    done <<< "$credentials"
    if [[ "$has_user" != 1 || "$has_password" != 1 ]]; then
      repository_missing_credentials
      return 1
    fi
  fi
  if [[ -d "$REPO_DIR/.git" ]]; then
    if git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
      if [[ -n "$GIT_USER" ]]; then
        git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
      fi
    else
      git -C "$REPO_DIR" remote add origin "$REPO_URL"
    fi
  fi
}

repository_network_git() {
  local error_file status
  error_file="$(mktemp)" || return 1
  # Git errors can contain the credential-bearing URL. Do not print raw stderr.
  if LC_ALL=C repository_git "$@" 2>"$error_file"; then
    rm -f -- "$error_file"
    return 0
  else
    status=$?
  fi
  if grep -Eiq 'Authentication failed|Invalid username or (password|token)|Invalid credentials|returned error: (401|403)|Authentication (required|denied)|could not read (Username|Password)' "$error_file"; then
    echo "Errore nel token."
  else
    echo "Operazione Git non riuscita. Controlla connessione, accesso al repository, branch e stato locale (git status)."
  fi
  rm -f -- "$error_file"
  return "$status"
}

repository_full() {
  mkdir -p "$BASE_DIR"

  # fix permissions of the whole repo BEFORE touching git
  if [ -d "$REPO_DIR" ]; then
    echo "🔑 Fixing permissions for existing repo (for git + ros)..."
    sudo chown -R "$USER":"$USER" "$REPO_DIR"
  fi

  repository_prepare_remote

  if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Existing repo in $REPO_DIR, aligning to origin/$BRANCH..."

    # Ignore executable-bit changes before updating an existing checkout.
    git -C "$REPO_DIR" config --local core.fileMode false

    repository_network_git -C "$REPO_DIR" fetch origin --prune
    git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || true
    git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
  else
    echo "📥 Cloning repo into $REPO_DIR..."
    repository_network_git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
  fi

  # Persist for both new clones and existing checkouts. The workspace chmod below
  # must not make unchanged source files appear modified in Git.
  git -C "$REPO_DIR" config --local core.fileMode false
}

repository_update() {
  echo "⬇️ 1) Updating code from GitHub..."
  if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Downloading updates from main (keeping local files)..."

    repository_prepare_remote
    git -C "$REPO_DIR" config --local core.fileMode false

    # Use pull with rebase and autostash:
    # Saves local modifications automatically, updates, and reapplies them on top of the new code.
    repository_network_git -C "$REPO_DIR" pull origin "$BRANCH" --rebase --autostash

    echo "Making the workspace writable by the container user..."
    sudo chmod -R 777 "$REPO_DIR/ros2_ws"

  else
    echo "❌ Error: Repo not found in $REPO_DIR."
    echo "👉 You must run the BASE SETUP script first to initialize the system!"
    exit 1
  fi
}

repository_configure() {
  # FIRST INSTALLATION: edit these values in the private copy sent to the Pi.
  # These settings apply to bootstrap, full and update when executed directly.
  USER_HOME="${AGIR_USER_HOME:-/home/boat}"
  DEPLOY_USER="${AGIR_USER:-boat}"
  REPO_DIR="${AGIR_REPO_DIR:-$USER_HOME/2025_SOFTWARE/sailing_ros}"
  BRANCH="${AGIR_BRANCH:-main}"
  GIT_USER="${AGIR_GIT_USER:-${GIT_USER:-}}"
  GIT_TOKEN="${AGIR_GIT_TOKEN:-${GIT_TOKEN:-}}"
  REPO_SLUG="agirsailing/sailing_ros"

  # Preserve deployment choices saved by an earlier bootstrap.
  if [[ -f "$REPO_DIR/DAY_BEFORE_REGATTA/config.local.sh" ]]; then
    source "$REPO_DIR/DAY_BEFORE_REGATTA/config.local.sh"
    USER_HOME="${AGIR_USER_HOME:-$USER_HOME}"
    DEPLOY_USER="${AGIR_USER:-$DEPLOY_USER}"
    REPO_DIR="${AGIR_REPO_DIR:-$REPO_DIR}"
    BRANCH="${AGIR_BRANCH:-$BRANCH}"
    GIT_USER="${AGIR_GIT_USER:-$GIT_USER}"
    GIT_TOKEN="${AGIR_GIT_TOKEN:-$GIT_TOKEN}"
  fi
  if [[ "$EUID" -eq 0 || "$HOME" != "$USER_HOME" ]]; then
    echo "Run this script as $DEPLOY_USER without sudo (home: $USER_HOME)."
    exit 1
  fi
  BASE_DIR="$(dirname "$REPO_DIR")"
  repository_validate_credentials
  if ! command -v git >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y git ca-certificates
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "Git installation failed."
    exit 1
  fi
}

repository_bootstrap() {
  repository_prepare_remote
  mkdir -p "$(dirname "$REPO_DIR")"
  if [[ -d "$REPO_DIR/.git" ]]; then
    # A repeated bootstrap must not discard local work like full setup does.
    git -C "$REPO_DIR" config --local core.fileMode false
    repository_network_git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" switch "$BRANCH"
    repository_network_git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
  else
    repository_network_git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
    git -C "$REPO_DIR" config --local core.fileMode false
  fi

  local setup_dir="$REPO_DIR/DAY_BEFORE_REGATTA"
  if [[ ! -f "$setup_dir/complete_setup.sh" || ! -f "$setup_dir/lib/common.sh" ]]; then
    echo "The downloaded branch is missing the modular setup. Push the new scripts and select the correct branch."
    exit 1
  fi
  if [[ ! -e "$setup_dir/config.local.sh" ]]; then
    (
      umask 077
      set -o noclobber
      {
        printf '# Local deployment settings; ignored by Git.\n'
        printf 'export AGIR_USER=%q\n' "$DEPLOY_USER"
        printf 'export AGIR_USER_HOME=%q\n' "$USER_HOME"
        printf 'export AGIR_REPO_DIR=%q\n' "$REPO_DIR"
        printf 'export AGIR_BRANCH=%q\n' "$BRANCH"
      } > "$setup_dir/config.local.sh"
    )
  fi
  echo "Repository ready in $REPO_DIR."
  echo "Copy mqtt_config.yaml into $REPO_DIR/ros2_ws/src/communication_web/config/ before continuing."
  printf 'Then run: bash %q\n' "$setup_dir/complete_setup.sh"
}

repository_main() {
  if [[ "$#" -gt 1 ]]; then
    echo "Usage: bash repository.sh [full|update]"
    exit 1
  fi
  local mode="${1:-bootstrap}"
  case "$mode" in
    bootstrap|full|update) ;;
    *) echo "Usage: bash repository.sh [full|update]"; exit 1 ;;
  esac
  repository_configure
  case "$mode" in
    bootstrap) repository_bootstrap ;;
    full) repository_full ;;
    update) repository_update ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  repository_main "$@"
fi
