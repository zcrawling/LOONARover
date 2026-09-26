#!/usr/bin/env bash
# Publish samples from the bench's forwarding socket; never open the MCU serial port.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
PARAMS=()
if [[ -f /etc/loonar/mcu-sensors.yaml ]]; then
  PARAMS+=(--params-file /etc/loonar/mcu-sensors.yaml)
fi
exec /usr/bin/python3 -m mcu_v2.ros_bridge --ros-args "${PARAMS[@]}" \
  -p "registry:=${1:?Registry path required}" \
  -p "socket:=${2:?Sample socket required}"
