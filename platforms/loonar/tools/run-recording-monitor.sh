#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
exec /usr/bin/python3 -m mcu_v2.recording_monitor "$@"
