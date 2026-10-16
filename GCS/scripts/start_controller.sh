#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --record-session ]]; then
    shift
    exec bash "$(dirname -- "${BASH_SOURCE[0]}")/../../tools/apriltag_gt/run_manual_session.sh" "$@"
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec python3 -B -m cli.xbox_control "$@"
