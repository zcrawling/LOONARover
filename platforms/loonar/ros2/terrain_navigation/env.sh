#!/usr/bin/env bash
# Source in every Pi terminal (including image subscribers).
export LOONAR_NAV_WS
LOONAR_NAV_WS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source /opt/ros/jazzy/setup.bash || return 1
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
source "$LOONAR_NAV_WS/install/pi5/setup.bash" || return 1
export FASTRTPS_DEFAULT_PROFILES_FILE="$LOONAR_NAV_WS/loonar_bringup/config/fastdds.xml"
