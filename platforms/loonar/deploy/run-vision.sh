#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
if [[ -d "$ROOT/common/ros2/loonar_target_vision/loonar_target_vision" ]]; then
  # Checkout launcher: use the code just pulled, without a stale colcon install.
  export PYTHONPATH="$ROOT/common/ros2/loonar_target_vision${PYTHONPATH:+:$PYTHONPATH}"
else
  source /opt/loonar/current/ros/install/setup.bash
fi
set -u
VIDEO_CONFIG=${LOONAR_VIDEO_CONFIG:-/etc/loonar/video.env}
VISION_CONFIG=${LOONAR_VISION_CONFIG:-/etc/loonar/vision.yaml}
[[ -r $VISION_CONFIG ]] || {
  echo "Missing vision config: $VISION_CONFIG. Run install-vision-runtime.sh MODEL_DIR on the Pi." >&2; exit 2;
}
source "$VIDEO_CONFIG"
GROUND_STATION_IP=10.254.254.2
[[ ${VIDEO_PROFILE:-} == low && ${VISION_ENABLED:-0} == 1 ]] || {
  echo "Set VIDEO_PROFILE=low and VISION_ENABLED=1 in $VIDEO_CONFIG" >&2; exit 2;
}
[[ ${VISION_FPS:-10} == 10 ]] || {
  echo 'VISION_FPS must match source_fps=10 in /etc/loonar/vision.yaml' >&2; exit 2;
}
VISION_PYTHON=${LOONAR_VISION_PYTHON:-/opt/loonar/vision-venv/bin/python}
[[ -x $VISION_PYTHON ]] || { echo "Missing Pi vision Python: $VISION_PYTHON" >&2; exit 127; }
export PYTHONNOUSERSITE=1
export YOLO_AUTOINSTALL=false
# The camera and reader are launched together. Wait for the socket instead of
# crashing shmsrc during normal camera startup. No inference fallback/backend.
VISION_SOCKET=${VISION_SOCKET:-/run/loonar/vision.sock}
echo "Waiting for camera shared frames: $VISION_SOCKET"
for ((attempt=0; attempt<300; attempt++)); do
  [[ -S $VISION_SOCKET ]] && break
  sleep 0.1
done
[[ -S $VISION_SOCKET ]] || { echo "Camera frame socket unavailable: $VISION_SOCKET" >&2; exit 2; }
echo "Starting NCNN / CPU; config=$VISION_CONFIG; python=$VISION_PYTHON"
exec "$VISION_PYTHON" -m loonar_target_vision.node \
  --ros-args --params-file "$VISION_CONFIG" \
  -p "vision_socket:=$VISION_SOCKET" \
  -p "ground_station_ip:=$GROUND_STATION_IP"
