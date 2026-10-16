#!/usr/bin/env bash
# User-started Pi stack with ROS samples and an optional, reconnecting Payload MCU.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
# Default GCS support includes continuous recording and AUTO fly lifecycle.
# Legacy explicit options remain available for the existing bench workflows.
if [[ $# == 0 && ${LOONAR_FLY_LEGACY_SUPPORT:-0} != 1 ]]; then
  exec bash "$ROOT/platforms/loonar/ros2/terrain_navigation/recording/run_pi.sh" --mode gcs
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
