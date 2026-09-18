#!/usr/bin/env bash
set -eo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/../../.venv-apriltag/bin/python" "$script_dir/run_distance_test.py" "$@"
