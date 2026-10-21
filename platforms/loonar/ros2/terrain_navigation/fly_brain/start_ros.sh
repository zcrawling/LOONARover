#!/usr/bin/env bash
set -eo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$FLY_DIR/../env.sh"
python3 "$LOONAR_NAV_WS/configure_auto.py" "${1:?registry}" "${2:?sample socket}"
export PYTHONPATH="$FLY_DIR${PYTHONPATH:+:$PYTHONPATH}"
children=()
vision_pid=
vision_runtime=
cleanup() {
  trap - EXIT INT TERM
  # Stop the shared-frame reader before its camera owner. SIGTERM also works
  # for background shells that inherited an ignored SIGINT.
  if [[ -n $vision_pid ]]; then kill -TERM "$vision_pid" 2>/dev/null || true; fi
  for child in "${children[@]}"; do
    if [[ $child != "$vision_pid" ]]; then kill -TERM "$child" 2>/dev/null || true; fi
  done
  for child in "${children[@]}"; do wait "$child" 2>/dev/null || true; done
  if [[ -n $vision_runtime ]]; then
    rm -f -- "$vision_runtime/frames.sock"
    rmdir -- "$vision_runtime" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Only MCU/base state is needed to observe cFS mode and keep manual telemetry.
# The supervisor owns ToF, TF, terrain, and monitoring nodes during AUTO.
sensor_nodes=true
[[ ${LOONAR_FLY_GCS:-0} != 1 ]] || sensor_nodes=false
ros2 launch loonar_bringup terrain.launch.py \
  params_file:="$LOONAR_NAV_WS/log/auto-runtime.yaml" \
  publish_tf:="$sensor_nodes" run_adapter:="$sensor_nodes" \
  run_stationary:="$sensor_nodes" run_safety:="$sensor_nodes" \
  run_base_io:=true enable_motion:="${LOONAR_FLY_DRIVE:-false}" \
  run_motion:=false run_navigator:=false run_perception:=false run_planner:=false &
children+=("$!")
if [[ ${LOONAR_FLY_GCS:-0} == 1 ]]; then
  python3 -m loonar_fly.supervisor --params-file "$LOONAR_NAV_WS/log/auto-runtime.yaml" &
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
if [[ ${LOONAR_FLY_GCS:-0} != 1 ]]; then
  python3 -m loonar_fly.terrain_node --ros-args --params-file "$LOONAR_NAV_WS/log/auto-runtime.yaml" &
  children+=("$!")
  critical+=("$!")
fi
if [[ ${LOONAR_FLY_CAMERA:-1} == 1 ]]; then
  mkdir -p "$FLY_DIR/log"
  root=$(cd -- "$LOONAR_NAV_WS/../../../.." && pwd)
  # Each manual launch owns its socket; no root-owned /run directory or
  # second systemd camera process is needed.
  # GCS detects objects in its decoded video; Pi inference is opt-in.
  vision_enabled=${LOONAR_FLY_VISION:-0}
  [[ $vision_enabled == 0 || $vision_enabled == 1 ]] || {
    echo 'LOONAR_FLY_VISION must be 0 or 1' >&2; exit 2;
  }
  : > "$FLY_DIR/log/vision.log"
  if [[ $vision_enabled == 1 ]]; then
    # A missing optional plugin must not take down the driving video.
    if (source "$root/platforms/loonar/deploy/loonar-camera-env.sh"
        gst-inspect-1.0 shmsink >/dev/null 2>&1); then
      vision_runtime=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/loonar-vision.XXXXXX")
    else
      vision_enabled=0
      echo 'RGB detection unavailable: GStreamer shmsink missing; camera continues.' | tee "$FLY_DIR/log/vision.log" >&2
    fi
  else
    echo 'RGB detection disabled by LOONAR_FLY_VISION=0.' > "$FLY_DIR/log/vision.log"
  fi
  # Reuse the existing camera's JPEG branch, without --record-all and its
  # second sensor launcher. This process is the single physical camera owner.
  printf '%s\n' 'VIDEO_SOURCE=libcamera' 'VIDEO_PROFILE=low' \
    'VIDEO_ENCODER_THREADS=1' 'VIDEO_PORT=5600' \
    "VISION_ENABLED=$vision_enabled" 'VISION_FPS=10' > "$FLY_DIR/log/camera.env"
  if [[ $vision_enabled == 1 ]]; then
    printf 'VISION_SOCKET=%q\n' "$vision_runtime/frames.sock" >> "$FLY_DIR/log/camera.env"
  fi
  LOONAR_VIDEO_CONFIG="$FLY_DIR/log/camera.env" \
    CAMERA_ROS_ENABLED=1 CAMERA_ROS_FPS="${LOONAR_FLY_CAMERA_FPS:-5}" \
    VIDEO_STREAM_ENABLED="$([[ ${LOONAR_FLY_GCS:-0} == 1 || -n ${LOONAR_FLY_VIDEO_IP:-} ]] && echo 1 || echo 0)" \
    GROUND_STATION_IP="${LOONAR_FLY_VIDEO_IP:-}" \
    bash "$root/platforms/loonar/deploy/run-video.sh" > "$FLY_DIR/log/camera.log" 2>&1 &
  children+=("$!")
  if [[ $vision_enabled == 1 ]]; then
    LOONAR_VIDEO_CONFIG="$FLY_DIR/log/camera.env" \
      bash "$root/platforms/loonar/deploy/run-vision.sh" > "$FLY_DIR/log/vision.log" 2>&1 &
    vision_pid=$!
    children+=("$vision_pid")
    echo "Pi NCNN detection starting; log: $FLY_DIR/log/vision.log"
  fi
fi
# Exit if either child fails; never leave a half-started sensor/body stack.
# Camera is optional: absent frames are marked unavailable, never synthesized.
if [[ -n $vision_pid ]]; then
  # Observe a failed detector once, but leave video and all critical tasks up.
  finished=
  code=0
  wait -n -p finished "${critical[@]}" "$vision_pid" || code=$?
  if [[ $finished != "$vision_pid" ]]; then exit "$code"; fi
  echo "RGB detection exited ($code); video/control continue. See $FLY_DIR/log/vision.log" >&2
  unset 'children[-1]'  # Already reaped; do not signal a reused PID on shutdown.
  vision_pid=
fi
wait -n "${critical[@]}"
