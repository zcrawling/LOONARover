#!/usr/bin/env bash
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$FLY_DIR/../../../../.." && pwd)
case "${1:-unit}" in
  unit)
    exec docker run --rm --user "$(id -u):$(id -g)" -v "$FLY_DIR:/fly" \
      loonar-fly-brain:783 /opt/fly-env/bin/python -m pytest tests/test_interface.py tests/test_drive.py tests/test_avoidance.py tests/test_vision.py tests/test_heading.py tests/test_gcs_pc.py -q ;;
  parity)
    exec docker run --rm --user "$(id -u):$(id -g)" -v "$FLY_DIR:/fly" \
      -e PYTHONPATH=/fly loonar-fly-brain:783 \
      /opt/fly-env/bin/python tests/stream_parity.py ;;
  ros|drive|terrain|gcs)
    test_script=ros_replay.py
    [[ ${1:-} != drive ]] || test_script=drive_ros.py
    [[ ${1:-} != terrain ]] || test_script=terrain_ros.py
    [[ ${1:-} != gcs ]] || test_script=gcs_ros.py
    # Dedicated domain; synthetic sensors cannot reach the physical rover.
    exec docker run --rm --user "$(id -u):$(id -g)" --network host \
      -v "$ROOT:/work" -w /work/platforms/loonar/ros2/terrain_navigation/fly_brain \
      -e ROS_DOMAIN_ID="${LOONAR_TEST_ROS_DOMAIN_ID:-219}" -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
      -e ROS_LOG_DIR=/work/platforms/loonar/ros2/terrain_navigation/fly_brain/log/ros-test \
      loonar-fly-brain:783 bash -c '
        source /opt/ros/jazzy/setup.bash
        source ../install/setup.bash
        export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
        exec /opt/fly-env/bin/python "tests/$1"' bash "$test_script" ;;
  *) echo 'Usage: bash test.sh [unit|parity|ros|drive|terrain|gcs]' >&2; exit 2 ;;
esac
