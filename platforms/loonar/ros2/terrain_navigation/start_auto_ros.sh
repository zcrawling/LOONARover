#!/usr/bin/env bash
# Called by motor_bench in place of the legacy sample bridge. No duplicate owner.
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
python3 "$LOONAR_NAV_WS/configure_auto.py" "${1:?registry}" "${2:?sample socket}"
exec ros2 launch loonar_bringup terrain.launch.py \
  params_file:="$LOONAR_NAV_WS/log/auto-runtime.yaml" \
  publish_tf:=true run_base_io:=true \
  enable_motion:=true calibration_confirmed:=true \
  autostart:=false gcs_auto_start:=true
