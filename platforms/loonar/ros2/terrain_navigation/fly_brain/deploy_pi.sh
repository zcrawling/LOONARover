#!/usr/bin/env bash
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$FLY_DIR/../run_gcs_auto.sh" "${1:-10.254.254.3}" --prepare-only
echo 'Pi: bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh'
echo 'PC: bash /home/sb/LOONAR/GCS/scripts/start_loonar_gcs.sh 10.254.254.3 → AUTO / STOP'
