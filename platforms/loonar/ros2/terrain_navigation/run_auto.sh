#!/usr/bin/env bash
# One Pi command: existing gateway/cFS/backend/video plus the terrain ROS stack.
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
for arg in "$@"; do
  if [[ $arg == --record-all ]]; then
    echo "--record-all starts another ToF driver; use --record with autonomy." >&2
    exit 2
  fi
done
if systemctl is-active --quiet loonar-tof.service; then
  echo "Stop loonar-tof.service before running autonomy (ToF USB is exclusive)." >&2
  exit 1
fi
test -f "$LOONAR_NAV_WS/terrain.local.yaml" || {
  echo "Missing $LOONAR_NAV_WS/terrain.local.yaml" >&2; exit 1;
}
export LOONAR_ROS_SAMPLE_LAUNCHER="$LOONAR_NAV_WS/start_auto_ros.sh"
echo "AUTO ready after sensor startup. Select GCS STOP, then AUTO; STOP halts navigation."
echo "ROS log: ~/loonar-motor-bench/runtime/sensors.log"
exec bash "$LOONAR_NAV_WS/../../tools/start-ground-support.sh" "$@"
