"""Offline regression checks: all system/Git/Docker commands are simulated.

Only private temporary copies are patched for the host/user checks.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
BASH = (str(Path('C:/Program Files/Git/bin/bash.exe')) if os.name == 'nt'
        else shutil.which('bash'))
FULL = 'complete_setup.sh'
QUICK = 'quick_setup.sh'

MOCKS = r'''
export PATH="/usr/bin:/bin:$PATH"
export USER=boat
record() { local entry="$*"; printf '%s\n' "${entry//$'\n'/ }" >> "$TEST_LOG"; }
uname() { echo aarch64; }
hostnamectl() { echo boat; }
id() { echo 'boat docker'; }
ping() { record "ping $*"; }
sleep() { record "sleep $*"; }
chmod() { record "chmod $*"; }
systemctl() {
  record "systemctl $*"
  if [[ "$1" == cat && "$TEST_SERVICE" == 0 ]]; then return 1; fi
  return 0
}
docker() {
  record "docker $*"
  case "$1 $2" in
    '--version ') echo 'Docker mock' ;;
    'container inspect') [[ "$TEST_CONTAINER" == 1 ]] ;;
    'inspect -f') echo true ;;
    'image inspect') echo "$TEST_IMAGE" ;;
    'exec '*)
      [[ "$TEST_FAIL" != ros_build ]] || return 7
      command mkdir -p "$TEST_REPO/ros2_ws/build" ;;
    'compose '*)
      if [[ "${*: -1}" == build || "${*: -1}" == --no-cache ]]; then
        [[ "$TEST_FAIL" != image_build ]] || return 8
      fi
      if [[ "$*" == *' up -d' ]]; then
        [[ "$TEST_FAIL" != start ]] || return 9
      fi ;;
  esac
}
git() {
  while [[ "$1" == -C || "$1" == -c ]]; do shift 2; done
  record "git $*"
  if [[ "$1" == fetch || "$1" == pull || "$1" == clone || "$1" == credential ]]; then
    [[ "${GIT_TERMINAL_PROMPT:-}" == 0 && "${GIT_ASKPASS:-}" == /bin/false &&
       "${GCM_INTERACTIVE:-}" == Never && "${GIT_SSH_COMMAND:-}" == *BatchMode=yes* ]] || return 96
    if [[ "$1" != credential && "$TEST_FAIL" == auth ]]; then
      echo 'fatal: Authentication failed for https://dummy:dummy_token@github.com/example.git' >&2
      return 128
    fi
  fi
  case "$1 $2" in
    'credential fill')
      command cat >/dev/null
      [[ "${TEST_NO_CREDENTIALS:-0}" != 1 ]] || return 1
      printf 'username=saved_user\npassword=saved_token\n'
      return 0 ;;
    'remote get-url') [[ -f "$TEST_ORIGIN" ]] && cat "$TEST_ORIGIN"; return $? ;;
    'remote set-url'|'remote add') printf '%s' "$4" > "$TEST_ORIGIN" ;;
    'fetch origin') [[ "$TEST_FAIL" != fetch ]] || return 10 ;;
    'pull origin') [[ "$TEST_FAIL" != pull ]] || return 11 ;;
    'clone -b')
      command mkdir -p "$TEST_REPO/.git" "$TEST_REPO/Docker/raspi_container" \
        "$TEST_REPO/ros2_ws/scripts" "$TEST_REPO/DAY_BEFORE_REGATTA"
      command touch "$TEST_REPO/Docker/raspi_container/compose.yaml" "$TEST_REPO/ros2_ws/scripts/build.sh"
      if [[ -n "${TEST_DOWNLOAD:-}" ]]; then
        command cp -R "$TEST_DOWNLOAD/." "$TEST_REPO/DAY_BEFORE_REGATTA/"
      else
        command cp "$TEST_SCRIPTS/run.sh" "$TEST_REPO/DAY_BEFORE_REGATTA/run.sh"
      fi ;;
  esac
  if [[ "$TEST_MUTATE" == 1 && ( "$1" == reset || "$1" == pull ) ]]; then
    printf 'echo "Loaded replaced module" >&2\nexit 99\n' > "$TEST_SCRIPTS/steps/workspace.sh"
  fi
  return 0
}
sudo() {
  case "$1" in
    docker|systemctl) "$@" ;;
    env) shift 2; "$@" ;;
    tee)
      shift
      local target="${*: -1}"
      if [[ "$target" == "$TEST_REPO/ros2_ws/build/.agir_image_id" ]]; then
        command tee "$target"
      else
        record "tee $*"
        command tee "$TEST_ROOT/$(basename "$target")"
      fi ;;
    rm)
      record "$*"
      shift 2
      local target
      for target in "$@"; do
        [[ "$target" == "$TEST_REPO"/ros2_ws/* ]] || return 97
      done
      command rm -rf -- "$@" ;;
    install)
      record "$*"
      command cp "$4" "$5" ;;
    *) record "$*" ;;
  esac
}
'''


@unittest.skipUnless(BASH and Path(BASH).exists(), 'Bash is required')
class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agir-setup-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home with spaces'
        self.repo = self.home / '2025_SOFTWARE/sailing_ros'
        self.scripts = self.repo / 'DAY_BEFORE_REGATTA'
        shutil.copytree(SCRIPTS, self.scripts,
                        ignore=shutil.ignore_patterns('tests', 'config.local.sh', '__pycache__'))
        (self.repo / '.git').mkdir()
        self.ws = self.repo / 'ros2_ws'
        (self.ws / 'scripts').mkdir(parents=True)
        (self.ws / 'scripts/build.sh').touch()
        (self.ws / 'build').mkdir()
        self.marker = self.ws / 'build/.agir_image_id'
        self.marker.write_text('image-current\n')
        container = self.repo / 'Docker/raspi_container'
        container.mkdir(parents=True)
        (container / 'compose.yaml').touch()
        self.log = self.root / 'commands.log'
        self.origin = self.root / 'origin'
        self.origin.write_text('https://github.com/agirsailing/sailing_ros.git')
        self.installed = self.root / 'installed-entrypoint.sh'
        self.installed.write_text('previous installed version')
        (self.root / 'systemd').mkdir()
        (self.root / 'bin').mkdir()
        (self.root / 'model').write_text('Raspberry Pi 4 Model B')
        (self.root / 'boot-config.txt').touch()
        (self.root / 'hosts').write_text('127.0.1.1 boat\n')
        self.mock_file = self.root / 'mocks.sh'
        self.mock_file.write_text(MOCKS, encoding='utf-8', newline='\n')
        self.env = dict(os.environ)
        for name in list(self.env):
            if name.startswith('AGIR_') or name in (
                    'GIT_USER', 'GIT_TOKEN', 'DISPLAY', 'WAYLAND_DISPLAY',
                    'XDG_RUNTIME_DIR', 'XAUTHORITY'):
                self.env.pop(name)
        self.env.update(
            BASH_ENV=self.mock_file.as_posix(), TEST_ROOT=self.root.as_posix(),
            TEST_LOG=self.log.as_posix(), TEST_REPO=self.repo.as_posix(),
            TEST_SCRIPTS=self.scripts.as_posix(), TEST_ORIGIN=self.origin.as_posix(),
            TEST_SERVICE='1', TEST_CONTAINER='1', TEST_IMAGE='image-current',
            TEST_FAIL='', TEST_MUTATE='0', AGIR_USER_HOME=self.home.as_posix(), AGIR_USER='boat')
        self.patch_fixture()

    def patch_fixture(self):
        """Substitute hardware paths and the user guard in private copies only."""
        for path in self.scripts.rglob('*.sh'):
            text = path.read_text(encoding='utf-8')
            text = text.replace('"$EUID" -eq 0 || "$HOME" != "$USER_HOME"', '1 -eq 0')
            text = text.replace('"$EUID" -ne 0', '1 -eq 0')
            text = text.replace('USER_HOME="/home/boat"', f'USER_HOME="{self.home.as_posix()}"')
            for before, after in (
                ('/proc/device-tree/model', (self.root / 'model').as_posix()),
                ('/boot/firmware/config.txt', (self.root / 'boot-config.txt').as_posix()),
                ('/etc/hosts', (self.root / 'hosts').as_posix()),
                ('/usr/local/bin/agir_regatta_start.sh', self.installed.as_posix()),
                ('/etc/systemd/system', (self.root / 'systemd').as_posix()),
                ('/usr/local/bin/$SCRIPT_NAME', (self.root / 'bin').as_posix() + '/$SCRIPT_NAME'),
            ):
                text = text.replace(before, after)
            path.write_text(text, encoding='utf-8', newline='\n')

    def run_setup(self, name=QUICK, *args, success=True):
        self.log.unlink(missing_ok=True)
        result = subprocess.run([BASH, str(self.scripts / name), *args],
                                env=self.env, capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        self.last_result = result
        return [' '.join(line.split()) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_order(self, log, *parts):
        cursor = 0
        for part in parts:
            while cursor < len(log) and part not in log[cursor]:
                cursor += 1
            self.assertLess(cursor, len(log), f'Missing or out of order: {part}\n{log}')
            cursor += 1

    def test_full_retains_host_hardware_reset_and_clean_build(self):
        log = self.run_setup(FULL)
        self.assert_order(log, 'systemctl stop agir_regatta.service', 'docker stop',
                          'apt-get update', 'systemctl start ssh', 'udevadm settle',
                          'git fetch origin --prune', 'git reset --hard origin/main',
                          'rm -rf', 'down --remove-orphans', 'build --no-cache',
                          'up -d', './build.sh --clean', 'docker image inspect',
                          'tee ' + self.installed.as_posix())
        self.assertTrue(log[-1].endswith(' stop'))
        self.assertIn('git config --local core.fileMode false', log)
        self.assertEqual(self.marker.read_text(), 'image-current\n')
        rules = (self.root / '99-boat-serial.rules').read_text()
        for port, alias in [('1.4', 'ultrasonic_left'), ('1.3', 'ultrasonic_right'), ('1.2', 'gps')]:
            self.assertIn(f'KERNELS=="1-{port}:1.0", SYMLINK+="{alias}"', rules)
        self.assertIn('enable_uart=1', (self.root / 'boot-config.txt').read_text())
        self.assertIn('dtoverlay=disable-bt', (self.root / 'boot-config.txt').read_text())

    def test_quick_keeps_rebase_incremental_and_service_stop_order(self):
        log = self.run_setup()
        self.assert_order(log, 'systemctl stop', ' stop', 'git pull origin main --rebase --autostash',
                          'chmod -R 777', ' build', 'docker image inspect', 'up -d',
                          './build.sh --incremental', 'tee ' + self.installed.as_posix())
        self.assertTrue(log[-1].endswith(' stop'))
        self.assertFalse(any('apt-get' in line or 'udevadm' in line or 'git reset' in line for line in log))
        self.assertFalse(any('--no-cache' in line or 'rm -rf' in line for line in log))

    def test_first_setup_from_folder_outside_missing_checkout(self):
        bootstrap = self.root / 'bootstrap scripts'
        shutil.copytree(self.scripts, bootstrap)
        self.assertTrue(self.repo.is_relative_to(self.root))
        shutil.rmtree(self.repo)
        self.scripts = bootstrap
        self.env['TEST_SCRIPTS'] = bootstrap.as_posix()
        log = self.run_setup(FULL)
        self.assert_order(log, 'git clone -b main', 'git config --local core.fileMode false',
                          'build --no-cache', './build.sh --clean')
        self.assertEqual(self.marker.read_text(), 'image-current\n')
        self.assertTrue(log[-1].endswith(' stop'))

    def test_explicit_clean_and_changed_or_missing_image(self):
        for args, marker in [(('--clean',), 'image-current\n'), ((), 'old-image\n'), ((), None)]:
            with self.subTest(args=args, marker=marker):
                if marker is None:
                    self.marker.unlink(missing_ok=True)
                else:
                    self.marker.write_text(marker)
                log = self.run_setup(QUICK, *args)
                self.assertTrue(any('./build.sh --clean' in line for line in log))
                self.assertEqual(self.marker.read_text(), 'image-current\n')

    def test_failed_ros_build_stops_and_preserves_last_successful_marker(self):
        self.env['TEST_FAIL'] = 'ros_build'
        self.marker.write_text('old-image\n')
        log = self.run_setup(success=False)
        self.assertTrue(log[-1].endswith(' stop'))
        self.assertFalse(any(line.startswith('install ') for line in log))
        self.assertEqual(self.marker.read_text(), 'old-image\n')
        self.assertEqual(self.installed.read_text(), 'previous installed version')
        log = self.run_setup(FULL, success=False)
        self.assertTrue(log[-1].endswith(' stop'))
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.installed.read_text(), 'previous installed version')

    def test_failed_start_runs_cleanup_and_does_not_build_ros(self):
        self.env['TEST_FAIL'] = 'start'
        for name in (FULL, QUICK):
            with self.subTest(name=name):
                log = self.run_setup(name, success=False)
                self.assertTrue(log[-1].endswith(' stop'))
                self.assertFalse(any('docker exec' in line for line in log))

    def test_git_and_image_failures_do_not_start_container(self):
        for name, failure in [(FULL, 'fetch'), (QUICK, 'pull'), (FULL, 'image_build'), (QUICK, 'image_build')]:
            with self.subTest(name=name, failure=failure):
                self.env['TEST_FAIL'] = failure
                log = self.run_setup(name, success=False)
                self.assertFalse(any(' up -d' in line for line in log))
                self.assertFalse(any('docker exec' in line for line in log))

    def test_absent_service_and_uninstalled_entrypoint_stay_absent(self):
        self.env['TEST_SERVICE'] = '0'
        self.installed.unlink()
        log = self.run_setup()
        self.assertFalse(any('systemctl stop' in line or line.startswith('install ') for line in log))
        self.assertFalse(self.installed.exists())

    def test_config_is_shared_and_local_branch_wins(self):
        (self.scripts / 'config.local.sh').write_text('export AGIR_BRANCH=dev\n')
        self.env['AGIR_BRANCH'] = 'other'
        log = self.run_setup()
        self.assertIn('git pull origin dev --rebase --autostash', log)
        log = self.run_setup(FULL)
        self.assertIn('git reset --hard origin/dev', log)

    def test_modules_are_loaded_before_git_replaces_them(self):
        self.env['TEST_MUTATE'] = '1'
        log = self.run_setup()
        self.assertTrue(any('docker exec' in line for line in log))
        self.assertTrue(log[-1].endswith(' stop'))

    def test_credentials_reuse_and_explicit_override_match_current_policy(self):
        self.run_setup(FULL)
        self.assertEqual(self.origin.read_text(), 'https://github.com/agirsailing/sailing_ros.git')
        self.env.update(AGIR_GIT_USER='dummy', AGIR_GIT_TOKEN='dummy_token')
        self.run_setup(FULL)
        self.assertEqual(self.origin.read_text(), 'https://dummy:dummy_token@github.com/agirsailing/sailing_ros.git')

    def test_missing_credentials_stop_all_repository_modes_without_network(self):
        self.env['TEST_NO_CREDENTIALS'] = '1'
        for args in ((), ('full',), ('update',)):
            with self.subTest(args=args):
                log = self.run_setup('steps/repository.sh', *args, success=False)
                self.assertIn('config.local.sh', self.last_result.stdout)
                self.assertFalse(any(line.startswith(('git fetch', 'git pull', 'git clone', 'git reset'))
                                     for line in log))

    def test_auth_failure_is_generic_and_does_not_expose_credentials(self):
        self.env['TEST_FAIL'] = 'auth'
        for args in ((), ('full',), ('update',)):
            with self.subTest(args=args):
                log = self.run_setup('steps/repository.sh', *args, success=False)
                output = self.last_result.stdout + self.last_result.stderr
                self.assertIn('Errore nel token.', output)
                self.assertNotIn('dummy_token', output)
                self.assertNotIn('scadut', output)
                self.assertFalse(any('git reset' in line or 'chmod -R 777' in line for line in log))

    def test_quick_accepts_replacement_credentials_from_local_file(self):
        self.env['TEST_NO_CREDENTIALS'] = '1'
        (self.scripts / 'config.local.sh').write_text(
            'AGIR_GIT_USER=dummy\nAGIR_GIT_TOKEN=dummy_token\n')
        log = self.run_setup()
        self.assertEqual(self.origin.read_text(),
                         'https://dummy:dummy_token@github.com/agirsailing/sailing_ros.git')
        self.assertIn('git pull origin main --rebase --autostash', log)

    def test_connection_failure_is_not_reported_as_token_failure(self):
        self.env['TEST_FAIL'] = 'fetch'
        self.run_setup('steps/repository.sh', 'full', success=False)
        self.assertIn('Operazione Git non riuscita', self.last_result.stdout)
        self.assertNotIn('Errore nel token', self.last_result.stdout)

    def test_existing_ssh_origin_does_not_require_https_token(self):
        self.env['TEST_NO_CREDENTIALS'] = '1'
        self.origin.write_text('git@github.com:agirsailing/sailing_ros.git')
        log = self.run_setup('steps/repository.sh', 'update')
        self.assertNotIn('git credential fill', log)

    def test_missing_repo_and_invalid_quick_arguments_stop_before_operations(self):
        (self.repo / '.git').rmdir()
        self.assertEqual(self.run_setup(success=False), [])
        self.assertEqual(self.run_setup(QUICK, '--unknown', success=False), [])

    def test_setup_and_quick_never_install_or_enable_autostart(self):
        for name in (FULL, QUICK):
            with self.subTest(name=name):
                log = self.run_setup(name)
                self.assertNotIn('systemctl enable agir_regatta.service', log)
                self.assertNotIn('systemctl start agir_regatta.service', log)
                self.assertNotIn('systemctl enable agir_wifi_guardian.service', log)
                self.assertEqual(list((self.root / 'systemd').iterdir()), [])

    def test_run_is_manual_and_uses_shared_network_target(self):
        self.env['AGIR_TARGET_IP'] = '192.168.1.1'
        log = self.run_setup('run.sh')
        self.assert_order(log, 'ping -c 1 -W 2 192.168.1.1', 'up -d', './run.sh live')
        self.assertFalse(any(line.startswith('systemctl') for line in log))

    def test_autostart_is_only_installed_by_explicit_command(self):
        log = self.run_setup('autostart_setup.sh')
        self.assert_order(log, 'systemctl stop agir_regatta.service', 'docker stop',
                          'systemctl daemon-reload', 'systemctl enable agir_regatta.service',
                          'systemctl start agir_regatta.service')
        unit = (self.root / 'systemd/agir_regatta.service').read_text()
        self.assertIn('User=boat', unit)
        self.assertIn(f'Environment="HOME={self.home.as_posix()}"', unit)
        self.assertIn(f'ExecStart=/bin/bash "{self.scripts.as_posix()}/run.sh"', unit)
        self.assertNotIn('agir_regatta_start.sh', unit)

    def test_autostart_validates_launcher_before_stopping_anything(self):
        (self.scripts / 'run.sh').unlink()
        self.assertEqual(self.run_setup('autostart_setup.sh', success=False), [])

    def test_network_installer_finds_check_script_from_other_directory(self):
        log = self.run_setup('network/install_wifi_guardian.sh')
        copied = self.root / 'bin/agir_wifi_check.sh'
        self.assertEqual(copied.read_bytes(), (self.scripts / 'network/agir_wifi_check.sh').read_bytes())
        self.assertIn('systemctl enable agir_wifi_guardian.service', log)
        self.assertNotIn('systemctl enable agir_regatta.service', log)

    def test_legacy_launcher_redirects_to_run_with_quoted_path(self):
        self.run_setup()
        installed = self.installed.read_text()
        self.assertTrue(installed.startswith('#!/usr/bin/env bash\nexec /bin/bash '))
        self.assertIn('/DAY_BEFORE_REGATTA/run.sh', installed)
        self.assertIn(r'home\ with\ spaces', installed)

    def test_standalone_repository_bootstrap_downloads_only_and_saves_settings(self):
        download = self.root / 'download'
        shutil.copytree(self.scripts, download)
        standalone = self.root / 'standalone'
        standalone.mkdir()
        shutil.copyfile(self.scripts / 'steps/repository.sh', standalone / 'repository.sh')
        self.assertTrue(self.repo.is_relative_to(self.root))
        shutil.rmtree(self.repo)
        self.scripts = standalone
        self.env.update(TEST_DOWNLOAD=download.as_posix(), AGIR_BRANCH='dev',
                        AGIR_GIT_USER='dummy', AGIR_GIT_TOKEN='dummy_token')
        log = self.run_setup('repository.sh')
        self.assertTrue(any('git clone -b dev' in line for line in log))
        self.assertIn('git config --local core.fileMode false', log)
        self.assertFalse(any('docker' in line or 'systemctl' in line for line in log))
        self.assertFalse(self.marker.exists())
        config = self.repo / 'DAY_BEFORE_REGATTA/config.local.sh'
        settings = config.read_text()
        self.assertIn('export AGIR_BRANCH=dev', settings)
        self.assertNotIn('dummy_token', settings)
        self.assertIn('Copy mqtt_config.yaml', self.last_result.stdout)

        # Re-running bootstrap preserves local settings and never hard-resets.
        config.write_text(settings + '# Keep my local configuration\n')
        log = self.run_setup('repository.sh')
        self.assertIn('git pull --ff-only origin dev', log)
        self.assertFalse(any('git reset' in line or 'docker' in line for line in log))
        self.assertTrue(config.read_text().endswith('# Keep my local configuration\n'))

    def test_repository_bootstrap_rejects_automatic_setup_option(self):
        log = self.run_setup('steps/repository.sh', '--setup', success=False)
        self.assertEqual(log, [])

    def test_repository_full_and_update_are_standalone_git_operations(self):
        for mode in ('full', 'update'):
            with self.subTest(mode=mode):
                log = self.run_setup('steps/repository.sh', mode)
                self.assertIn('git config --local core.fileMode false', log)
                if mode == 'full':
                    self.assert_order(log, 'core.fileMode false', 'git fetch origin --prune',
                                      'git reset --hard origin/main')
                else:
                    self.assert_order(log, 'core.fileMode false',
                                      'git pull origin main --rebase --autostash', 'chmod -R 777')
                    self.assertFalse(any('git reset' in line for line in log))
                self.assertFalse(any('docker' in line or 'systemctl' in line for line in log))

    def test_repository_modes_reject_invalid_arguments_before_operations(self):
        for args in (('--unknown',), ('full', 'update')):
            with self.subTest(args=args):
                self.assertEqual(self.run_setup('steps/repository.sh', *args, success=False), [])
        (self.repo / '.git').rmdir()
        self.assertEqual(self.run_setup('steps/repository.sh', 'update', success=False), [])

    def test_external_setup_passes_nonexported_configuration_to_git_process(self):
        external = self.root / 'external scripts'
        shutil.copytree(self.scripts, external)
        self.scripts = external
        (external / 'config.local.sh').write_text(
            'AGIR_BRANCH=dev\nAGIR_GIT_USER=dummy\nAGIR_GIT_TOKEN=dummy_token\n')
        log = self.run_setup(FULL)
        self.assertIn('git reset --hard origin/dev', log)
        self.assertEqual(self.origin.read_text(),
                         'https://dummy:dummy_token@github.com/agirsailing/sailing_ros.git')

    def test_setup_invokes_repository_as_a_command_with_the_requested_mode(self):
        (self.scripts / 'steps/repository.sh').write_text('''#!/usr/bin/env bash
repository_validate_credentials() { :; }
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  record "repository command $*"
  exit 23
fi
''', encoding='utf-8', newline='\n')
        for script, mode in ((FULL, 'full'), (QUICK, 'update')):
            with self.subTest(script=script):
                log = self.run_setup(script, success=False)
                self.assertEqual(self.last_result.returncode, 23)
                self.assertIn(f'repository command {mode}', log)
                self.assertFalse(any(' up -d' in line for line in log))


if __name__ == '__main__':
    unittest.main(verbosity=2)
