#!/usr/bin/env bash
# User-started Pi stack with ROS samples and an optional, reconnecting Payload MCU.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
# --gcs-ip selects the control/video/ROS recipient. Observer PCs receive status only.
network_args=()
bench_args=()
video=0
gcs_ip=${GROUND_STATION_IP:-}
while (( $# )); do
  case "$1" in
    --gcs-ip) gcs_ip=${2:?Missing PC IPv4 address}; shift 2 ;;
    --video-ip) gcs_ip=${2:?Missing PC IPv4 address}; video=1; shift 2 ;;
    --status-ip) network_args+=(--status-ip "${2:?Missing observer IPv4 address}"); shift 2 ;;
    --video) video=1; shift ;;
    --help|-h)
      echo 'Usage: start-ground-support.sh --gcs-ip PC_IP [--status-ip OBSERVER_IP] [--video] [bench options]'
      echo 'Explicit --record and --record-all retain their separate meanings.'
      exit 0 ;;
    *) bench_args+=("$1"); shift ;;
  esac
done
if [[ -z $gcs_ip ]]; then
  read -r -p 'Ground station PC IPv4: ' gcs_ip
fi
# Validate before installing any configuration or launching hardware processes.
/usr/bin/python3 "$ROOT/platforms/loonar/tools/network/configure.py" --gcs-ip "$gcs_ip" "${network_args[@]}" --dry-run >/dev/null
# Apply the selected peers to the existing firewall and status service as well.
# sudo may prompt here; SSH (port 22) and unrelated firewall tables are preserved.
if [[ ${LOONAR_NETWORK_CONFIGURED:-0} != 1 ]]; then
  sudo bash "$ROOT/platforms/loonar/tools/setup-network.sh" --gcs-ip "$gcs_ip" "${network_args[@]}"
fi
export GROUND_STATION_IP="$gcs_ip" LOONAR_FLY_VIDEO_IP="$gcs_ip" ROS_STATIC_PEERS="$gcs_ip"
set -- "${bench_args[@]}"
# Default GCS support starts AUTO services without a recorder.
# --video uses the same camera owner as the AUTO sensor stack.
# Keep specialized bench options and the explicit legacy override available.
if [[ ${LOONAR_FLY_LEGACY_SUPPORT:-0} != 1 ]] &&
   [[ $# == 0 ]]; then
  export LOONAR_ROS_SAMPLE_LAUNCHER="$ROOT/platforms/loonar/ros2/terrain_navigation/fly_brain/start_ros.sh"
  export LOONAR_FLY_GCS=1 LOONAR_FLY_DRIVE=true LOONAR_FLY_CAMERA=1
  # Do not inherit raw capture from a previous recording session.
  unset LOONAR_CAPTURE_SESSION LOONAR_CAPTURE_ASYNC_CONTROL
  echo 'Starting GCS support: video, AUTO standby. Recording OFF.' >&2
  set --
else
  echo 'Legacy bench mode: GCS AUTO driving is unavailable in this launch.' >&2
fi
export PYTHONPATH="$ROOT/platforms/loonar/tools${PYTHONPATH:+:$PYTHONPATH}"
if [[ ${LOONAR_FLY_GCS:-0} != 1 && $video == 1 ]]; then
  set -- --video-ip "$gcs_ip" "$@"
fi
exec python3 -m mcu_v2.motor_bench \
  --ros-samples \
  --registry "$HOME/loonar-motor-bench/control.json" \
  --payload-device "${PAYLOAD_DEVICE:-/dev/serial/by-id/usb-Teensyduino_USB_Serial_21147480-if00}" \
  --gateway-bin "$ROOT/build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd" \
  --cfs-dir "$ROOT/build/gcs-test/cFS/build-native_std/exe/cpu1" "$@"
