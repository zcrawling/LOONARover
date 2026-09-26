#!/usr/bin/env bash
# Run on LOONAR: record available ROS topics to local storage until Ctrl+C.
set -eo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
OUTPUT=${1:-"$HOME/loonar-bags/drive_$(date +%Y%m%d_%H%M%S_%N)"}
mkdir -p -- "$(dirname -- "$OUTPUT")"
echo "Recording ROS topics locally: $OUTPUT"
exec ros2 bag record --storage mcap --output "$OUTPUT" \
  --disable-keyboard-controls --max-bag-size 1073741824 \
  --qos-profile-overrides-path "$ROOT/platforms/loonar/config/tof-bag-qos.yaml" \
  --all
