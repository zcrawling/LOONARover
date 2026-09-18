#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source /opt/loonar/current/ros/install/setup.bash
exec ros2 launch loonar_localization loonar_minimal_ekf.launch.py
