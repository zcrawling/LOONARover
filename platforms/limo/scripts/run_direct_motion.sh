#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$tool_dir/../tools/direct_motion.py" "$@"
