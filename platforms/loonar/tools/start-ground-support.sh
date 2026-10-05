#!/usr/bin/env bash
# User-started Pi stack with ROS samples and an optional, reconnecting Payload MCU.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export PYTHONPATH="$ROOT/platforms/loonar/tools${PYTHONPATH:+:$PYTHONPATH}"
if [[ ${1:-} == --video ]]; then
  [[ -n ${SSH_CONNECTION:-} ]] || { echo 'Use --video-ip GCS_IPV4 when not connected over SSH.' >&2; exit 2; }
  shift
  set -- --video-ip "${SSH_CONNECTION%% *}" "$@"
fi
exec python3 -m mcu_v2.motor_bench \
  --ros-samples \
  --registry "$HOME/loonar-motor-bench/control.json" \
  --payload-device "${PAYLOAD_DEVICE:-/dev/serial/by-id/usb-Teensyduino_USB_Serial_20356570-if00}" \
  --gateway-bin "$ROOT/build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd" \
  --cfs-dir "$ROOT/build/gcs-test/cFS/build-native_std/exe/cpu1" "$@"
