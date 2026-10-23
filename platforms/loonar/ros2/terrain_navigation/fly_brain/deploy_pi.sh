#!/usr/bin/env bash
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$FLY_DIR/../run_gcs_auto.sh" "${1:?Usage: deploy_pi.sh PI_IP}" --prepare-only
echo 'Pi: bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --gcs-ip PC_IP'
echo "PC: bash GCS/scripts/start_loonar_gcs.sh --rover-ip $1 → AUTO / STOP"
