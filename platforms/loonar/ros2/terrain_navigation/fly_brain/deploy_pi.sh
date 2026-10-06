#!/usr/bin/env bash
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$FLY_DIR/../run_gcs_auto.sh" "${1:-10.254.254.3}" --prepare-only
echo 'Fly shadow files copied. On Pi run: bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/fly_brain/run_pi.sh'
