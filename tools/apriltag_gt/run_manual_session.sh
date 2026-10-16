#!/usr/bin/env bash
set -euo pipefail
tool_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${LOONAR_APRILTAG_PYTHON:-$tool_dir/../../.venv-apriltag/bin/python}" "$tool_dir/run_manual_session.py" "$@"
