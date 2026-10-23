#!/usr/bin/env bash
# Existing GCS UI, routed through the Pi recording proxy. No GCS source edits.
set -euo pipefail
RECORD_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$RECORD_DIR/../../../../.." && pwd)
cd "$ROOT/GCS"
# real_app owns backend.lock and removes stale backend.sock after acquiring it.
# A leftover socket alone does not mean a backend is running.
children=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${children[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${children[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 -B -m backend.real_app --host "${1:?Usage: run_pc.sh PI_IP}" --port 7444 --config "$RECORD_DIR/gcs.toml" &
children+=("$!")
sleep 1
kill -0 "${children[0]}"
python3 -B -m webui.server --attach --config "$RECORD_DIR/gcs.toml" &
children+=("$!")
echo '지상국: http://127.0.0.1:8080 — 수동 명령은 Pi 녹화 프록시 7444를 경유합니다.'
wait -n "${children[@]}"
