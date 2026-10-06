#!/usr/bin/env bash
# Existing backend/gateway/cFS, with a ROS-only brain interface substituted.
set -eo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help ]]; then
  echo 'Usage: bash run_pi.sh [--drive] [--max-speed 0.2] [--drive-seconds N] [--video-ip PC_IP] [--no-camera]'
  echo '--drive: operator-supervised motion, local obstacle avoidance, no GCS/cFS. Ctrl+C stops.'
  exit 0
fi
source "$FLY_DIR/../env.sh"
export LOONAR_FLY_CAMERA=1 LOONAR_FLY_VIDEO_IP=''
export LOONAR_FLY_DRIVE=false LOONAR_FLY_DRIVE_SECONDS=0
export LOONAR_FLY_MAX_SPEED=0.2
bench_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --drive) export LOONAR_FLY_DRIVE=true; shift ;;
    --max-speed)
      export LOONAR_FLY_MAX_SPEED="${2:?missing speed}"
      python3 -c 'import math,sys; n=float(sys.argv[1]); assert math.isfinite(n) and 0<n<=.2' "$2"
      shift 2 ;;
    --drive-seconds)
      export LOONAR_FLY_DRIVE_SECONDS="${2:?missing seconds}"
      python3 -c 'import math,sys; n=float(sys.argv[1]); assert math.isfinite(n) and n>0' "$2"
      shift 2 ;;
    --video-ip)
      export LOONAR_FLY_VIDEO_IP="${2:?missing PC IP}"
      python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$2"
      shift 2 ;;
    --no-camera) export LOONAR_FLY_CAMERA=0; shift ;;
    --record-all|--record-video|--video)
      echo 'Fly mode owns the camera/ToF pipelines. Use --video-ip for streaming.' >&2; exit 2 ;;
    --record|--encoder-verify) bench_args+=("$1"); shift ;;
    *) echo "Unknown/unsupported option: $1" >&2; exit 2 ;;
  esac
done
if systemctl is-active --quiet loonar-tof.service; then
  echo 'Stop loonar-tof.service before starting (exclusive ToF USB owner).' >&2; exit 1
fi
test -f "$LOONAR_NAV_WS/terrain.local.yaml"
export LOONAR_ROS_SAMPLE_LAUNCHER="$FLY_DIR/start_ros.sh"
if [[ $LOONAR_FLY_DRIVE == true ]]; then
  echo "Supervised fly drive: max $LOONAR_FLY_MAX_SPEED m/s, local obstacle avoidance. Fresh terrain/sensors/brain -> turn or advance. Ctrl+C stops."
  export PYTHONPATH="$LOONAR_NAV_WS/../../tools${PYTHONPATH:+:$PYTHONPATH}"
  # Deliberately no cFS process: drive_node exclusively owns cfs.sock for mode selection.
  exec python3 -m mcu_v2.motor_bench --ros-samples \
    --registry "$HOME/loonar-motor-bench/control.json" \
    --gateway-bin "$LOONAR_NAV_WS/../../../../build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd" \
    "${bench_args[@]}"
fi
echo 'Fly brain SHADOW mode. Motor actuation disabled; original navigator disabled.'
exec bash "$LOONAR_NAV_WS/../../tools/start-ground-support.sh" "${bench_args[@]}"
