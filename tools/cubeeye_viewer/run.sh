#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sdk_default="$HOME/Downloads/x86_64-ubuntu-linux-22_04_v2.5.11_20250417/x86_64-ubuntu-linux-22_04/release"
exec "$tool_dir/../../.venv-apriltag/bin/python" "$tool_dir/viewer.py" --sdk "${CUBEEYE_SDK:-$sdk_default}" "$@"
