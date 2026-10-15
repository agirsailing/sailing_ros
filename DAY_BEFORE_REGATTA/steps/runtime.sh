#!/usr/bin/env bash
# Loaded by lib/common.sh before Git changes the checkout.

runtime_stop_service() {
  # An explicit systemctl stop suppresses Restart=always without disabling boot startup.
  if systemctl cat "$REGATTA_SERVICE" >/dev/null 2>&1; then
    sudo systemctl stop "$REGATTA_SERVICE"
  fi
}

runtime_stop_full() {
  runtime_stop_service
  # Stopping the docker exec client alone does not guarantee that ROS has stopped.
  if command -v docker >/dev/null 2>&1 && sudo docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    sudo docker stop "$CONTAINER_NAME"
  fi
}

runtime_stop_quick() {
  runtime_stop_service
  compose stop
}

runtime_refresh_entrypoint() {
  # Compatibility for services installed by the old boot installer.
  # New services invoke run.sh in the checkout directly. Refresh only an existing
  # legacy launcher; never install, enable or start a service from setup/update.
  if [[ -f /usr/local/bin/agir_regatta_start.sh ]]; then
    printf '#!/usr/bin/env bash\nexec /bin/bash %q\n' "$REPO_DIR/DAY_BEFORE_REGATTA/run.sh" \
      | sudo tee /usr/local/bin/agir_regatta_start.sh >/dev/null
    sudo chmod 0755 /usr/local/bin/agir_regatta_start.sh
  fi
}
