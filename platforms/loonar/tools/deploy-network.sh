#!/usr/bin/env bash
# Copy configurable network paths and build cFS. Does not start rover processes.
set -euo pipefail
if [[ ${1:-} == --help || $# != 1 ]]; then
  echo 'Usage: bash platforms/loonar/tools/deploy-network.sh USER@PI_IP'
  exit 0
fi
TARGET=$1
[[ $TARGET =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo 'Invalid SSH target' >&2; exit 2; }
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
ssh -o ConnectTimeout=8 "$TARGET" 'mkdir -p ~/LOONAR'
rsync -az --files-from=- ./ "$TARGET:LOONAR/" <<'FILES'
cfs/apps/ground_link/fsw/src/loonar_ground_link_app.c
common/video/loonar-video-stream
common/video/camera_ros.py
common/video/camera_stream.py
common/video/camera_control.py
common/ros2/loonar_target_vision/config/vision.yaml
common/ros2/loonar_target_vision/loonar_target_vision/node.py
platforms/loonar/tools/start-ground-support.sh
platforms/loonar/tools/setup-network.sh
platforms/loonar/tools/pi_status_broadcast.py
platforms/loonar/tools/network/configure.py
platforms/loonar/tools/network/policy.nft
platforms/loonar/tools/network/apply.sh
platforms/loonar/tools/mcu_v2/motor_bench.py
platforms/loonar/deploy/run-video.sh
platforms/loonar/deploy/run-vision.sh
platforms/loonar/ros2/terrain_navigation/env.sh
platforms/loonar/ros2/terrain_navigation/fly_brain/start_ros.sh
platforms/loonar/ros2/terrain_navigation/fly_brain/run_pi.sh
platforms/loonar/ros2/terrain_navigation/runtime/thermal_sensor.py
platforms/loonar/ros2/terrain_navigation/recording/loonar_recording/proxy.py
platforms/loonar/ros2/terrain_navigation/recording/loonar_recording/session.py
platforms/loonar/systemd/loonar-cfs.service
GCS/cli/status_udp.py
GCS/backend/hardware_status.py
GCS/cli/pi_hardware_probe.py
GCS/cli/hardware_monitor.py
GCS/cli/diagnostics.py
tools/cubeeye_stream/send.py
FILES
ssh "$TARGET" 'bash ~/LOONAR/platforms/loonar/deploy/prepare-ground-control.sh'
echo 'Build complete. On Pi: bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --gcs-ip PC_IP --video'
