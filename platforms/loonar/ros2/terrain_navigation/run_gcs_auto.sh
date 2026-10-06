#!/usr/bin/env bash
# One PC command: copy sources, rebuild on Pi, then open the existing GCS.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo "Usage: bash run_gcs_auto.sh PI_IP [--prepare-only]"
  exit 0
fi
PI_IP=${1:?Usage: bash run_gcs_auto.sh PI_IP [--prepare-only]}
[[ $PI_IP =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo "Invalid Pi host" >&2; exit 2; }
[[ $# -le 2 && (${2:-} == '' || ${2:-} == --prepare-only) ]] || exit 2
NAV_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$NAV_DIR/../../../.." && pwd)
TARGET="loonar@$PI_IP"
SOCKET_DIR=$(mktemp -d /tmp/loonar-auto-ssh.XXXXXX)
SSH_OPTS=(-o ConnectTimeout=8 -o ControlMaster=auto -o ControlPersist=60 -o "ControlPath=$SOCKET_DIR/control")
cleanup() {
  ssh "${SSH_OPTS[@]}" -O exit "$TARGET" >/dev/null 2>&1 || true
  rmdir "$SOCKET_DIR" 2>/dev/null || true
}
trap cleanup EXIT
# Ask SSH for credentials once; rsync/build reuse that authenticated connection.
ssh "${SSH_OPTS[@]}" "$TARGET" 'set -e
if pgrep -f "[r]os2 launch loonar_bringup terrain.launch.py" >/dev/null; then
  echo "Stop the running terrain launch before deploying." >&2
  exit 1
fi
mkdir -p ~/LOONAR/platforms/loonar/ros2 ~/LOONAR/platforms/loonar/tools/mcu_v2'
printf -v RSYNC_RSH '%q ' ssh "${SSH_OPTS[@]}"
rsync -az -e "$RSYNC_RSH" \
  --exclude='build/' --exclude='install/' --exclude='log/' \
  --exclude='__pycache__/' --exclude='.pytest_cache/' \
  --exclude='*.log' --exclude='*.local.yaml' --exclude='*.local.json' \
  --exclude='*.local.urdf' --exclude='*.local.sh' \
  --exclude='bags/' --exclude='reports/' \
  --exclude='terrain_navigation/fly_brain/vendor/' \
  --exclude='terrain_navigation/fly_brain/.venv/' \
  --exclude='terrain_navigation/fly_brain/cache/' \
  "$NAV_DIR" "$NAV_DIR/../loonar_description" \
  "$TARGET:LOONAR/platforms/loonar/ros2/"
rsync -az -e "$RSYNC_RSH" "$ROOT/platforms/loonar/tools/mcu_v2/ros_samples.py" \
  "$TARGET:LOONAR/platforms/loonar/tools/mcu_v2/"
ssh "${SSH_OPTS[@]}" "$TARGET" 'bash -s' <<'REMOTE'
set -eo pipefail
source /opt/ros/jazzy/setup.bash
cd ~/LOONAR/platforms/loonar/ros2/terrain_navigation
colcon build --base-paths . ../loonar_description \
  --build-base build/pi5 --install-base install/pi5 --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DCUBEEYE_SDK=/opt/loonar/vendor/cubeeye/2.5.9/release
source ./env.sh
test -f terrain.local.yaml
python3 -c 'from pathlib import Path; from configure_auto import configure; configure(Path.home()/"loonar-motor-bench/control.json",Path.home()/"loonar-motor-bench/runtime/ros-samples.sock",Path.cwd())'
REMOTE
cleanup
trap - EXIT
echo "Pi deploy/build complete. Run terrain_navigation/run_auto.sh on Pi, then select GCS STOP -> AUTO."
if [[ ${2:-} != --prepare-only ]]; then
  exec bash "$ROOT/GCS/scripts/start_loonar_gcs.sh" "$PI_IP"
fi
