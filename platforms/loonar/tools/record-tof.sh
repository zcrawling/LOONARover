#!/usr/bin/env bash
# Record the ToF cloud locally on the Pi. Ctrl+C finalizes the bag.
set -eo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
OUTPUT=${1:-"$HOME/loonar-bags/tof_$(date +%Y%m%d_%H%M%S)"}
if [[ $# -gt 0 ]]; then shift; fi
mkdir -p -- "$(dirname -- "$OUTPUT")"
echo "Recording to $OUTPUT; Ctrl+C stops and finalizes the bag."
echo 'ToF topics plus /tf and /tf_static; extra topics can follow the output path.'
exec ros2 bag record --storage mcap --output "$OUTPUT" \
  --disable-keyboard-controls \
  --max-bag-size 1073741824 \
  --qos-profile-overrides-path "$ROOT/platforms/loonar/config/tof-bag-qos.yaml" \
  --topics /tof/depth/points /tof/status /tf /tf_static "$@"
