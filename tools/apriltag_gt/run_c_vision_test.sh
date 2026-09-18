#!/usr/bin/env bash
set -eo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$tool_dir/../../.venv-apriltag/bin/python" "$tool_dir/run_c_vision_test.py" "$@"
