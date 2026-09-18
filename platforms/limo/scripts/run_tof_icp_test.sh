#!/usr/bin/env bash
set -eo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
source "$HOME/agilex_ws/install/setup.bash"
source "$HOME/loonar_ws/install/setup.bash"
exec python3 "$script_dir/../tools/run_tof_trial.py" "$@"
