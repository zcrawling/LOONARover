#!/usr/bin/env bash
set -eo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
# The development laptop owns AprilTag; only the Pi owns ROS/control.
if [[ "$(uname -m)" != "aarch64" ]]; then
  exec "$ROOT/.venv-apriltag/bin/python" "$ROOT/tools/apriltag_gt/run_loonar_c_vision.py" "$@"
fi
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
export PYTHONPATH="$ROOT/platforms/loonar/tools:$ROOT/common/ros2/loonar_localization:${PYTHONPATH:-}"
exec /usr/bin/python3 -m c_acc.run_trial "$@"
