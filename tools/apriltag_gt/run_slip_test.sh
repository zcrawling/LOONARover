#!/usr/bin/env bash
# Integrated sand trial; no motion occurs until the user runs this entrypoint.
set -eo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$tool_dir/run_c_vision_test.sh" --cruise 1 "$@"
