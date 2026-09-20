#!/usr/bin/env bash
# Run on the Pi once after copying source changes; compile only, no hardware access.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
exec python3 "$ROOT/tools/gcs_test/run.py" --build-only --skip-tests --jobs 2
