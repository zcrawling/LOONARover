#!/usr/bin/env bash
set -euo pipefail

source /opt/ros/humble/setup.bash
if [[ -f "${HOME}/agilex_ws/install/setup.bash" ]]; then
  source "${HOME}/agilex_ws/install/setup.bash"
fi

test -c /dev/ttylimo
ros2 pkg executables limo_base | grep -qx 'limo_base limo_base'
printf 'ttylimo: %s\n' "$(readlink -f /dev/ttylimo)"
printf 'ROS graph check (start limo_base before expecting these topics):\n'
ros2 topic list -t | grep -E '^/(cmd_vel|limo_status|wheel/odom|imu) ' || true
