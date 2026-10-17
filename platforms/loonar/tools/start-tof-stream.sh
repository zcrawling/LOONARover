#!/usr/bin/env bash
# Manual standalone preview. No systemd registration or GCS integration.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
exec /usr/bin/python3 "$ROOT/tools/cubeeye_stream/send.py" "$@"
