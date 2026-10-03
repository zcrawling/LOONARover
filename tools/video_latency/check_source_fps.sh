#!/usr/bin/env bash
# Run on the Pi only after the video benchmark releases the camera.
set -euo pipefail
source /opt/loonar/current/lib/loonar-camera-env.sh
run_check() {
    local name=$1
    shift
    printf '\nCHECK %s\n' "$name"
    set +e
    timeout --signal=INT --kill-after=3 12 gst-launch-1.0 -e -v "$@"
    result=$?
    set -e
    [[ $result == 0 || $result == 124 ]]
}
run_check camera_only_1080 \
    libcamerasrc ! video/x-raw,width=1920,height=1080,framerate=30/1,format=NV12 \
    ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false fps-update-interval=1000
run_check original_encoder_1080 \
    libcamerasrc ! video/x-raw,width=1920,height=1080,framerate=30/1,format=NV12 \
    ! queue max-size-buffers=2 leaky=downstream \
    ! videoconvert ! video/x-raw,format=I420 \
    ! x264enc tune=zerolatency speed-preset=ultrafast threads=4 bitrate=5000 key-int-max=30 bframes=0 \
    ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false fps-update-interval=1000
