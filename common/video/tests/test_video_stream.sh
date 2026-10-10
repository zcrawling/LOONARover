#!/usr/bin/env bash
set -euo pipefail
STREAM="$1"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/pi.env" <<'EOF'
GROUND_STATION_IP=192.0.2.1
VIDEO_SOURCE=libcamera
VIDEO_PROFILE=medium
EOF
PI_PIPELINE="$(LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'libcamerasrc' <<<"$PI_PIPELINE"
grep -q 'bitrate=3000' <<<"$PI_PIPELINE"
grep -q 'width=1280' <<<"$PI_PIPELINE"
grep -q 'format=NV12' <<<"$PI_PIPELINE"
if grep -q 'videoconvert' <<<"$PI_PIPELINE"; then
  echo "libcamera unnecessarily converts NV12" >&2
  exit 1
fi

cat >"$TMP_DIR/limo.env" <<'EOF'
GROUND_STATION_IP=192.0.2.1
VIDEO_SOURCE=v4l2
VIDEO_DEVICE=/dev/v4l/by-id/example
VIDEO_PROFILE=low
EOF
LIMO_PIPELINE="$(LOONAR_VIDEO_CONFIG="$TMP_DIR/limo.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'v4l2src' <<<"$LIMO_PIPELINE"
grep -q 'image/jpeg' <<<"$LIMO_PIPELINE"
grep -q 'videocrop' <<<"$LIMO_PIPELINE"
grep -q 'bitrate=1000' <<<"$LIMO_PIPELINE"
grep -q 'videoconvert' <<<"$LIMO_PIPELINE"
grep -q 'format=I420' <<<"$LIMO_PIPELINE"

cat >"$TMP_DIR/bad.env" <<'EOF'
GROUND_STATION_IP=192.0.2.1
VIDEO_SOURCE=unknown
VIDEO_PROFILE=medium
EOF
if LOONAR_VIDEO_CONFIG="$TMP_DIR/bad.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM" >/dev/null 2>&1; then
  echo "invalid source unexpectedly succeeded" >&2
  exit 1
fi

REC_PIPELINE="$(VIDEO_STREAM_ENABLED=0 VIDEO_RECORD_PATH="$TMP_DIR/camera test.ts" LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'filesink' <<<"$REC_PIPELINE"
if grep -q 'udpsink' <<<"$REC_PIPELINE"; then exit 1; fi
BOTH_PIPELINE="$(VIDEO_RECORD_PATH="$TMP_DIR/both.ts" LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'filesink' <<<"$BOTH_PIPELINE"
grep -q 'udpsink' <<<"$BOTH_PIPELINE"
[[ $(grep -o 'libcamerasrc' <<<"$BOTH_PIPELINE" | wc -l) == 1 ]]
[[ $(grep -o 'x264enc' <<<"$BOTH_PIPELINE" | wc -l) == 1 ]]
VISION_PIPELINE="$(VISION_ENABLED=1 LOONAR_VIDEO_CONFIG="$TMP_DIR/limo.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'shmsink' <<<"$VISION_PIPELINE"
grep -q 'format=BGR' <<<"$VISION_PIPELINE"
grep -q 'format=I420' <<<"$VISION_PIPELINE"
grep -q 'max-size-buffers=1' <<<"$VISION_PIPELINE"
[[ $(grep -o 'v4l2src' <<<"$VISION_PIPELINE" | wc -l) == 1 ]]
[[ $(grep -o 'x264enc' <<<"$VISION_PIPELINE" | wc -l) == 1 ]]
VISION_BOTH="$(VISION_ENABLED=1 VIDEO_RECORD_PATH="$TMP_DIR/vision.ts" LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'filesink' <<<"$VISION_BOTH"
grep -q 'udpsink' <<<"$VISION_BOTH"
grep -q 'shmsink' <<<"$VISION_BOTH"
[[ $(grep -o 'libcamerasrc' <<<"$VISION_BOTH" | wc -l) == 1 ]]
[[ $(grep -o 'x264enc' <<<"$VISION_BOTH" | wc -l) == 1 ]]
BAG_ONLY="$(CAMERA_ROS_ENABLED=1 VIDEO_STREAM_ENABLED=0 LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
grep -q 'appsink' <<<"$BAG_ONLY"
grep -q 'jpegenc' <<<"$BAG_ONLY"
if grep -Eq 'udpsink|x264enc|filesink' <<<"$BAG_ONLY"; then exit 1; fi
[[ $(grep -o 'libcamerasrc' <<<"$BAG_ONLY" | wc -l) == 1 ]]
BAG_BOTH="$(CAMERA_ROS_ENABLED=1 CAMERA_ROS_FPS=10 VIDEO_RECORD_PATH="$TMP_DIR/bag.ts" VISION_ENABLED=1 LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM")"
for element in appsink filesink udpsink shmsink; do grep -q "$element" <<<"$BAG_BOTH"; done
[[ $(grep -o 'libcamerasrc' <<<"$BAG_BOTH" | wc -l) == 1 ]]
[[ $(grep -o 'x264enc' <<<"$BAG_BOTH" | wc -l) == 1 ]]
if CAMERA_ROS_FPS=0 LOONAR_VIDEO_CONFIG="$TMP_DIR/pi.env" LOONAR_VIDEO_DRY_RUN=1 bash "$STREAM" >/dev/null 2>&1; then exit 1; fi
