#!/usr/bin/env bash
set -euo pipefail
source /opt/loonar/current/lib/loonar-camera-env.sh
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
if [[ -f "$ROOT/common/video/loonar-video-stream" ]]; then
  exec bash "$ROOT/common/video/loonar-video-stream"
fi
exec /opt/loonar/current/lib/loonar-video-stream
