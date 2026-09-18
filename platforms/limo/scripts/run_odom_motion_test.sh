#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
if [[ -f "$HOME/agilex_ws/install/setup.bash" ]]; then
  source "$HOME/agilex_ws/install/setup.bash"
fi
source "$HOME/loonar_ws/install/setup.bash"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/../tools/run_odom_motion_test.py" "$@"
