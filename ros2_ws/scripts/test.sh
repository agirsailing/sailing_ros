#!/usr/bin/env bash
set -euo pipefail

# =========================
# Config
# =========================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(dirname "$SCRIPT_DIR")"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-2}"

BUILD_FIRST=1
CLEAN_BUILD=0
VERBOSE_RESULTS=1
PACKAGES=()

# =========================
# Helpers
# =========================
usage() {
  echo "Usage:"
  echo "  ./test.sh                         # build workspace, run all tests"
  echo "  ./test.sh can_bus                 # build workspace, run tests for one package"
  echo "  ./test.sh can_bus flap_control    # build workspace, run tests for selected packages"
  echo "  ./test.sh --no-build can_bus      # run selected tests without rebuilding first"
  echo "  ./test.sh --clean-build           # clean and rebuild using scripts/build.sh first"
  echo "  ./test.sh --summary               # print compact test result summary"
  echo
  echo "Environment:"
  echo "  PARALLEL_WORKERS=4 ./test.sh      # override colcon parallel workers"
  exit "${1:-0}"
}

source_ros_environment() {
  # ROS setup scripts may read optional environment variables before defining them.
  # Keep nounset for our script, but disable it while sourcing ROS environments.
  set +u

  if [[ -f /opt/ros/jazzy/setup.bash ]]; then
    source /opt/ros/jazzy/setup.bash
  fi

  if [[ -f "$WS_DIR/install/setup.bash" ]]; then
    source "$WS_DIR/install/setup.bash"
  fi

  set -u
}

build_workspace() {
  echo "Building workspace before tests..."
  cd "$WS_DIR"

  if [[ "$CLEAN_BUILD" -eq 1 ]]; then
    echo "Clean build requested."
    bash "$SCRIPT_DIR/build.sh"
    return
  fi

  source_ros_environment

  if [[ -f "$WS_DIR/tools/gen_endpoints.py" ]]; then
    echo "Generating ROS endpoints..."
    python3 "$WS_DIR/tools/gen_endpoints.py"
  fi

  local build_args=(build --symlink-install --base-paths src --parallel-workers "$PARALLEL_WORKERS")

  if [[ ${#PACKAGES[@]} -gt 0 ]]; then
    build_args+=(--packages-up-to "${PACKAGES[@]}")
  fi

  colcon "${build_args[@]}"
}

run_tests() {
  echo "Running ROS 2 tests..."
  cd "$WS_DIR"
  source_ros_environment

  local colcon_args=(test --base-paths src --event-handlers console_direct+ --parallel-workers "$PARALLEL_WORKERS")

  if [[ ${#PACKAGES[@]} -gt 0 ]]; then
    colcon_args+=(--packages-select "${PACKAGES[@]}")
    echo "Selected packages: ${PACKAGES[*]}"

    local package
    for package in "${PACKAGES[@]}"; do
      local package_result_base="$WS_DIR/build/$package/test_results"
      if [[ -d "$package_result_base" ]]; then
        rm -rf "$package_result_base"
      fi
    done
  else
    echo "Selected packages: all"
  fi

  colcon "${colcon_args[@]}"
}

print_results() {
  echo "Collecting test results..."
  cd "$WS_DIR"

  local result_args=(test-result)
  if [[ "$VERBOSE_RESULTS" -eq 1 ]]; then
    result_args+=(--verbose)
  fi

  if [[ ${#PACKAGES[@]} -gt 0 ]]; then
    local package
    for package in "${PACKAGES[@]}"; do
      local package_result_base="$WS_DIR/build/$package/test_results"
      local python_result_base="$WS_DIR/build/$package"

      if [[ -d "$package_result_base" ]]; then
        echo "Results for package: $package"
        colcon "${result_args[@]}" --test-result-base "$package_result_base"
      elif [[ -f "$python_result_base/pytest.xml" ]]; then
        echo "Results for Python package: $package"
        colcon "${result_args[@]}" --test-result-base "$python_result_base"
      else
        echo "No test results found for package: $package"
        echo "Expected directory: $package_result_base"
        echo "Or Python result file: $python_result_base/pytest.xml"
      fi
    done
    print_results_note
    return
  fi

  colcon "${result_args[@]}"
  print_results_note
}

print_results_note() {
  echo
  echo "Note:"
  echo "  GTest unit tests appear as '*.gtest.xml' entries in the report and as"
  echo "  CTest lines like 'test_payload_parser ... Passed' in the test output."
  echo "  Skipped tests are usually disabled/unavailable ament linters, not skipped"
  echo "  package unit tests. Use '--verbose' output to see the exact source."
}

# =========================
# Args
# =========================
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage 0
      ;;
    --no-build)
      BUILD_FIRST=0
      shift
      ;;
    --clean-build)
      CLEAN_BUILD=1
      shift
      ;;
    --summary)
      VERBOSE_RESULTS=0
      shift
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        PACKAGES+=("$1")
        shift
      done
      ;;
    -*)
      echo "Unknown option: $1"
      usage 1
      ;;
    *)
      PACKAGES+=("$1")
      shift
      ;;
  esac
done

# =========================
# Main
# =========================
echo "Workspace: $WS_DIR"

if [[ "$BUILD_FIRST" -eq 1 ]]; then
  build_workspace
else
  echo "Skipping build."
fi

run_tests
print_results

echo "Tests completed."
