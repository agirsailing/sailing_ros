#!/usr/bin/env bash
# Standalone Git step: no arguments for bootstrap, full or update for setup.
# Functions may also be loaded by lib/common.sh without executing operations.

repository_validate_credentials() {
  # Accept placeholders left in older local copies as unset values.
  if [[ "$GIT_USER" == INSERT_* ]]; then GIT_USER=""; fi
  if [[ "$GIT_TOKEN" == INSERT_* ]]; then GIT_TOKEN=""; fi
  if [[ ( -n "$GIT_USER" && -z "$GIT_TOKEN" ) || ( -z "$GIT_USER" && -n "$GIT_TOKEN" ) ]]; then
    echo "Provide both GIT_USER and GIT_TOKEN to replace credentials, or leave both empty to reuse Git authentication."
    exit 1
  fi
}

repository_full() {
  mkdir -p "$BASE_DIR"

  # fix permissions of the whole repo BEFORE touching git
  if [ -d "$REPO_DIR" ]; then
    echo "🔑 Fixing permissions for existing repo (for git + ros)..."
    sudo chown -R "$USER":"$USER" "$REPO_DIR"
  fi

  # With no override, Git itself uses any configured credential helper (or prompts
  # when needed). Existing origin URLs may also contain credentials or use SSH.
  REPO_URL="https://github.com/${REPO_SLUG}.git"
  if [[ -n "$GIT_USER" ]]; then
    REPO_URL="https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git"
  fi

  if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Existing repo in $REPO_DIR, aligning to origin/$BRANCH..."

    # Ignore executable-bit changes before updating an existing checkout.
    git -C "$REPO_DIR" config --local core.fileMode false

    # Rebase/reset do not remove .git/config. Preserve saved origin credentials
    # and SSH URLs unless the user explicitly supplies a replacement pair.
    if git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
      if [[ -n "$GIT_USER" ]]; then
        git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
        echo "Updated origin with the supplied GitHub credentials."
      else
        echo "Reusing existing origin and Git authentication."
      fi
    else
      git -C "$REPO_DIR" remote add origin "$REPO_URL"
    fi

    if ! git -C "$REPO_DIR" fetch origin --prune; then
      echo "Fetch failed: check connectivity, repository access and whether saved credentials have expired."
      echo "For an HTTPS token replacement, supply both GIT_USER and GIT_TOKEN and rerun setup."
      exit 1
    fi
    git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null || true
    git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
  else
    echo "📥 Cloning repo into $REPO_DIR..."
    git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
  fi

  # Persist for both new clones and existing checkouts. The workspace chmod below
  # must not make unchanged source files appear modified in Git.
  git -C "$REPO_DIR" config --local core.fileMode false
}

repository_update() {
  echo "⬇️ 1) Updating code from GitHub..."
  if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Downloading updates from main (keeping local files)..."

    git -C "$REPO_DIR" config --local core.fileMode false

    # Use pull with rebase and autostash:
    # Saves local modifications automatically, updates, and reapplies them on top of the new code.
    git -C "$REPO_DIR" pull origin "$BRANCH" --rebase --autostash

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
  REPO_URL="https://github.com/${REPO_SLUG}.git"
  if [[ -n "$GIT_USER" ]]; then
    REPO_URL="https://${GIT_USER}:${GIT_TOKEN}@github.com/${REPO_SLUG}.git"
  fi
  mkdir -p "$(dirname "$REPO_DIR")"
  if [[ -d "$REPO_DIR/.git" ]]; then
    # A repeated bootstrap must not discard local work like full setup does.
    if git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
      if [[ -n "$GIT_USER" ]]; then
        git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
      fi
    else
      git -C "$REPO_DIR" remote add origin "$REPO_URL"
    fi
    git -C "$REPO_DIR" config --local core.fileMode false
    git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" switch "$BRANCH"
    git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
  else
    git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
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
