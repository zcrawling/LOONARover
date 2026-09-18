#!/usr/bin/env bash
# Camera-only AprilTag preview. No SSH, ROS, recording, or motion commands.
set -eo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
camera=/dev/video0
for candidate in /dev/v4l/by-id/*C920*video-index0; do
    if [[ -e "$candidate" ]]; then
        camera="$candidate"
        break
    fi
done
exec "$tool_dir/../../.venv-apriltag/bin/python" "$tool_dir/gt.py" inspect \
    --camera "$camera" --width 1920 --height 1080 --fps 30 \
    --focus 0 "$@"
