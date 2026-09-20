#!/usr/bin/env bash

set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

VIDEO_FILTER=()
if [[ $# -eq 1 && $1 == --rotate-left ]]; then
    VIDEO_FILTER=(-vf transpose=cclock)
elif [[ $# -ne 0 ]]; then
    echo 'Usage: start_video.sh [--rotate-left]' >&2
    exit 2
fi

# Single receiver even when GCS is started more than once.
exec 9>"$RUNTIME_DIR/video.lock"
if ! flock -n 9; then
    printf '[LOONAR] 영상 수신이 이미 실행 중입니다.\n'
    exit 0
fi
# Also respect a receiver opened directly before this launcher.
if pgrep -f '[f]fplay .*udp://@:5600' >/dev/null 2>&1; then
    printf '[LOONAR] 영상 수신이 이미 실행 중입니다.\n'
    exit 0
fi

if ! command -v ffplay >/dev/null 2>&1; then
    show_error "ffplay가 설치되어 있지 않습니다. ffmpeg 패키지가 필요합니다."
    exit 1
fi

printf '[LOONAR] UDP 5600 영상 수신을 기다립니다. 종료: Ctrl+C\n'
printf '[LOONAR] 영상이 나오지 않으면 로버의 송신 대상 IP를 확인하세요.\n'
exec ffplay -hide_banner -loglevel warning -fflags nobuffer -flags low_delay \
    -framedrop -probesize 32 -analyzeduration 0 "${VIDEO_FILTER[@]}" udp://@:5600
