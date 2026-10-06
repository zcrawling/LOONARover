#!/usr/bin/env bash
# ToF + CAD TF observation by default. MCU/gateway ownership remains external.
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
if [[ ! -f "$LOONAR_NAV_WS/terrain.local.yaml" ]]; then
  echo "Missing $LOONAR_NAV_WS/terrain.local.yaml; see README.md." >&2
  exit 1
fi
exec ros2 launch loonar_bringup terrain.launch.py \
  params_file:="$LOONAR_NAV_WS/terrain.local.yaml" \
  publish_tf:=true "$@"
