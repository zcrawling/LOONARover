#!/usr/bin/env bash
set -eo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$FLY_DIR/../env.sh"
python3 "$LOONAR_NAV_WS/configure_auto.py" "${1:?registry}" "${2:?sample socket}"
export PYTHONPATH="$FLY_DIR${PYTHONPATH:+:$PYTHONPATH}"
children=()
cleanup() {
  trap - EXIT INT TERM
  for child in "${children[@]}"; do kill -INT "$child" 2>/dev/null || true; done
  for child in "${children[@]}"; do wait "$child" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ros2 launch loonar_bringup terrain.launch.py \
  params_file:="$LOONAR_NAV_WS/log/auto-runtime.yaml" \
  publish_tf:=true run_base_io:=true enable_motion:="${LOONAR_FLY_DRIVE:-false}" \
  run_motion:=false run_navigator:=false run_perception:=false run_planner:=false &
children+=("$!")
if [[ ${LOONAR_FLY_GCS:-0} == 1 ]]; then
  python3 -m loonar_fly.supervisor &
elif [[ ${LOONAR_FLY_DRIVE:-false} == true ]]; then
  python3 -m loonar_fly.drive_node \
    --gateway-socket "$(dirname -- "$2")/gateway/cfs.sock" \
    --max-drive-seconds "${LOONAR_FLY_DRIVE_SECONDS:-0}" \
    --max-speed "${LOONAR_FLY_MAX_SPEED:-0.2}" &
else
  python3 -m loonar_fly.body_node &
fi
children+=("$!")
critical=("${children[@]}")
python3 -m loonar_fly.terrain_node --ros-args --params-file "$LOONAR_NAV_WS/log/auto-runtime.yaml" &
children+=("$!")
critical+=("$!")
if [[ ${LOONAR_FLY_CAMERA:-1} == 1 ]]; then
  mkdir -p "$FLY_DIR/log"
  # Reuse the existing camera's JPEG branch, without --record-all and its
  # second sensor launcher. This process is the single physical camera owner.
  printf '%s\n' 'VIDEO_SOURCE=libcamera' 'VIDEO_PROFILE=low' \
    'VIDEO_ENCODER_THREADS=1' 'VIDEO_PORT=5600' > "$FLY_DIR/log/camera.env"
  root=$(cd -- "$LOONAR_NAV_WS/../../../.." && pwd)
  LOONAR_VIDEO_CONFIG="$FLY_DIR/log/camera.env" \
    CAMERA_ROS_ENABLED=1 CAMERA_ROS_FPS="${LOONAR_FLY_CAMERA_FPS:-5}" \
    VIDEO_STREAM_ENABLED="$([[ -n ${LOONAR_FLY_VIDEO_IP:-} ]] && echo 1 || echo 0)" \
    GROUND_STATION_IP="${LOONAR_FLY_VIDEO_IP:-}" \
    bash "$root/platforms/loonar/deploy/run-video.sh" > "$FLY_DIR/log/camera.log" 2>&1 &
  children+=("$!")
fi
# Exit if either child fails; never leave a half-started sensor/body stack.
# Camera is optional: absent frames are marked unavailable, never synthesized.
wait -n "${critical[@]}"
