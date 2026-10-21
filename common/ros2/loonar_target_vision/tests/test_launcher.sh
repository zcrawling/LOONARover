#!/usr/bin/env bash
# Exercise the real launcher with process doubles; no ROS, camera or motors.
set -euo pipefail
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
BASE=$(cd -- "${TMPDIR:-/tmp}" && pwd)
WORK=$(mktemp -d "$BASE/vision-launch-test.XXXXXX")
cleanup() {
  case "$WORK" in "$BASE"/vision-launch-test.*) rm -rf -- "$WORK" ;; esac
}
trap cleanup EXIT
NAV="$WORK/platforms/loonar/ros2/terrain_navigation"
FLY="$NAV/fly_brain"
mkdir -p "$FLY" "$WORK/platforms/loonar/deploy" "$WORK/bin" "$WORK/run"
cp "$REPO/platforms/loonar/ros2/terrain_navigation/fly_brain/start_ros.sh" "$FLY/"
printf 'export LOONAR_NAV_WS=%q\n' "$NAV" > "$NAV/env.sh"
: > "$WORK/platforms/loonar/deploy/loonar-camera-env.sh"
cat > "$WORK/bin/python3" <<'SH'
#!/usr/bin/env bash
[[ $1 == */configure_auto.py ]] && exit 0
trap 'exit 0' TERM
while :; do sleep .05; done
SH
cat > "$WORK/bin/ros2" <<'SH'
#!/usr/bin/env bash
trap 'exit 0' TERM
# Must outlive the failed detector: control keeps running until its own exit.
sleep 1
echo control-finished >> "$TRACE"
exit 42
SH
cat > "$WORK/bin/gst-inspect-1.0" <<'SH'
#!/usr/bin/env bash
exit "${PLUGIN_STATUS:-0}"
SH
cat > "$WORK/platforms/loonar/deploy/run-video.sh" <<'SH'
#!/usr/bin/env bash
set -eu
source "$LOONAR_VIDEO_CONFIG"
echo "camera $VISION_ENABLED ${VISION_SOCKET:-none} $VIDEO_STREAM_ENABLED" >> "$TRACE"
LOONAR_VIDEO_DRY_RUN=1 bash "$REAL_STREAM" > "$TRACE.pipeline"
trap 'echo camera-stopped >> "$TRACE"; exit 0' TERM
while :; do sleep .05; done
SH
cat > "$WORK/platforms/loonar/deploy/run-vision.sh" <<'SH'
#!/usr/bin/env bash
set -eu
source "$LOONAR_VIDEO_CONFIG"
[[ $VISION_ENABLED == 1 && $VISION_FPS == 10 ]]
echo "vision $VISION_SOCKET" >> "$TRACE"
if [[ ${DETECTOR_FAIL:-0} == 1 ]]; then exit 7; fi
trap 'echo vision-stopped >> "$TRACE"; exit 0' TERM
while :; do sleep .05; done
SH
chmod +x "$WORK/bin/"*
export PATH="$WORK/bin:$PATH" REAL_STREAM="$REPO/common/video/loonar-video-stream"
export XDG_RUNTIME_DIR="$WORK/run" LOONAR_FLY_GCS=1 LOONAR_FLY_CAMERA=1
unset LOONAR_FLY_VIDEO_IP LOONAR_FLY_VISION VISION_ENABLED VISION_SOCKET

run_case() {
  export TRACE="$WORK/$1.trace"
  local code=0
  timeout 10 bash "$FLY/start_ros.sh" registry samples > "$TRACE.log" 2>&1 || code=$?
  [[ $code == 42 ]] || { cat "$TRACE.log"; echo "Unexpected exit $code in $1"; exit 1; }
  grep -q control-finished "$TRACE"
  grep -q camera-stopped "$TRACE"
  [[ $(grep -c '^camera ' "$TRACE") == 1 ]]
  grep -q udpsink "$TRACE.pipeline"
  grep -q bag_camera "$TRACE.pipeline"
  [[ $(grep -o libcamerasrc "$TRACE.pipeline" | wc -l) == 1 ]]
  [[ -z $(ls -A "$WORK/run") ]] || { echo 'Leaked vision runtime directory'; exit 1; }
}

export DETECTOR_FAIL=0 PLUGIN_STATUS=0
run_case gcs_detection_default
! grep -q '^vision ' "$TRACE"
! grep -q shmsink "$TRACE.pipeline"

export LOONAR_FLY_VISION=1
run_case normal
grep -q shmsink "$TRACE.pipeline"
grep -q vision-stopped "$TRACE"
camera_socket=$(awk '$1=="camera" {print $3}' "$TRACE")
vision_socket=$(awk '$1=="vision" {print $2}' "$TRACE")
[[ $camera_socket == "$vision_socket" && -n $camera_socket ]]

export DETECTOR_FAIL=1
run_case detector_failure
grep -q 'RGB detection exited (7); video/control continue' "$TRACE.log"
grep -q shmsink "$TRACE.pipeline"

export PLUGIN_STATUS=1
run_case missing_plugin
! grep -q '^vision ' "$TRACE"
! grep -q shmsink "$TRACE.pipeline"
grep -q 'shmsink missing' "$FLY/log/vision.log"

export PLUGIN_STATUS=0 LOONAR_FLY_VISION=0
run_case explicitly_disabled
! grep -q '^vision ' "$TRACE"
! grep -q shmsink "$TRACE.pipeline"
grep -q 'disabled' "$FLY/log/vision.log"
echo 'PASS: shared camera, socket agreement, failure isolation, shutdown, opt-out'
