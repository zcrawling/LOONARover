#!/usr/bin/env bash
set -eo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source /opt/ros/jazzy/setup.bash
colcon build --base-paths . ../loonar_description --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
colcon test --packages-select loonar_terrain_core
colcon test-result --verbose
# All publishers in this test domain are simulated. No base_io or SDK is launched.
ROS_DOMAIN_ID="${LOONAR_TEST_DOMAIN_ID:-97}" python3 -m pytest tests -v --junitxml=log/ros-integration.xml
ROS_DOMAIN_ID="${LOONAR_TEST_DOMAIN_ID:-97}" python3 tests/check_launch.py
