#!/usr/bin/env bash
# Source in every Pi terminal (including image subscribers).
export LOONAR_NAV_WS
LOONAR_NAV_WS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source /opt/ros/jazzy/setup.bash || return 1
if [[ -z ${GROUND_STATION_IP:-} && -f /etc/loonar/network.env ]]; then
  set -a
  source /etc/loonar/network.env
  set +a
fi
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_STATIC_PEERS="${GROUND_STATION_IP:-${ROS_STATIC_PEERS:-}}"
unset ROS_LOCALHOST_ONLY
source "$LOONAR_NAV_WS/install/pi5/setup.bash" || return 1
export FASTRTPS_DEFAULT_PROFILES_FILE="$LOONAR_NAV_WS/loonar_bringup/config/fastdds.xml"
