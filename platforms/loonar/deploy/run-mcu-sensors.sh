#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
exec /usr/bin/python3 -m mcu_v2.ros_bridge --ros-args --params-file /etc/loonar/mcu-sensors.yaml
