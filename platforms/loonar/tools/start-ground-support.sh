#!/usr/bin/env bash
# User-started Pi stack with ROS samples and an optional, reconnecting Payload MCU.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
# Default GCS support starts AUTO services without a recorder.
# --video uses the same camera owner as the AUTO sensor stack.
# Keep specialized bench options and the explicit legacy override available.
if [[ ${LOONAR_FLY_LEGACY_SUPPORT:-0} != 1 ]] &&
   { [[ $# == 0 ]] || [[ $# == 1 && $1 == --video ]]; }; then
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
if [[ ${1:-} == --video ]]; then
  shift
  set -- --video-ip 10.254.254.2 "$@"
fi
exec python3 -m mcu_v2.motor_bench \
  --ros-samples \
  --registry "$HOME/loonar-motor-bench/control.json" \
  --payload-device "${PAYLOAD_DEVICE:-/dev/serial/by-id/usb-Teensyduino_USB_Serial_21147480-if00}" \
  --gateway-bin "$ROOT/build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd" \
  --cfs-dir "$ROOT/build/gcs-test/cFS/build-native_std/exe/cpu1" "$@"
