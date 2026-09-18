#!/usr/bin/env bash
set -eo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$tool_dir${PYTHONPATH:+:$PYTHONPATH}"
exec "$tool_dir/../../.venv-apriltag/bin/python" -m unittest discover -s "$tool_dir/tests" -p 'test_*.py' "$@"
