#!/usr/bin/env bash
# Start the fixed, depth-only DaBai configuration used for LIMO validation.
set -eo pipefail

set +u
source /opt/ros/humble/setup.bash

vendor_workspace="${LIMO_VENDOR_WS:-$HOME/agilex_ws}"
if [[ -f "$vendor_workspace/install/setup.bash" ]]; then
  # shellcheck disable=SC1090
  source "$vendor_workspace/install/setup.bash"
fi

workspace_root="${LOONAR_LIMO_WS:-$HOME/loonar_ws}"
if [[ -f "$workspace_root/install/setup.bash" ]]; then
  # shellcheck disable=SC1090
  source "$workspace_root/install/setup.bash"
fi
set -u

exec ros2 launch loonar_limo_tof limo_dabai_tof.launch.py "$@"
