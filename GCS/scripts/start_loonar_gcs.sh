#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export GCS_CONFIG="$HERE/../config/loonar.toml"
export GCS_VIDEO_ROTATE_LEFT=1
exec bash "$HERE/start_gcs.sh" "$@"
