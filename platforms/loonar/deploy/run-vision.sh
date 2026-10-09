#!/usr/bin/env bash
set -euo pipefail
source /opt/ros/jazzy/setup.bash
source /opt/loonar/current/ros/install/setup.bash
source /etc/loonar/video.env
: "${GROUND_STATION_IP:?GROUND_STATION_IP is required}"
[[ ${VIDEO_PROFILE:-} == low && ${VISION_ENABLED:-0} == 1 ]] || {
  echo 'Set VIDEO_PROFILE=low and VISION_ENABLED=1 in /etc/loonar/video.env' >&2; exit 2;
}
[[ ${VISION_FPS:-10} == 10 ]] || {
  echo 'VISION_FPS must match source_fps=10 in /etc/loonar/vision.yaml' >&2; exit 2;
}
VISION_PYTHON=${LOONAR_VISION_PYTHON:-/opt/loonar/vision-venv/bin/python}
[[ -x $VISION_PYTHON ]] || { echo "Missing Pi vision Python: $VISION_PYTHON" >&2; exit 127; }
export PYTHONNOUSERSITE=1
export YOLO_AUTOINSTALL=false
exec "$VISION_PYTHON" -m loonar_target_vision.node \
  --ros-args --params-file /etc/loonar/vision.yaml \
  -p "ground_station_ip:=$GROUND_STATION_IP"
