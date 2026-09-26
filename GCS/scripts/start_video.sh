#!/usr/bin/env bash

set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

VIDEO_FILTER=()
RECORD=0
COMPASS=0
ROTATE_LEFT=0
for option in "$@"; do
    case "$option" in
        --rotate-left) VIDEO_FILTER=(-vf transpose=cclock); ROTATE_LEFT=1 ;;
        --record) RECORD=1 ;;
        --compass) COMPASS=1 ;;
        *) echo 'Usage: start_video.sh [--rotate-left] [--record] [--compass]' >&2; exit 2 ;;
    esac
done

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

if [[ $COMPASS == 0 ]] && ! command -v ffplay >/dev/null 2>&1; then
    show_error "ffplay가 설치되어 있지 않습니다. ffmpeg 패키지가 필요합니다."
    exit 1
fi

printf '[LOONAR] UDP 5600 영상 수신을 기다립니다. 종료: Ctrl+C\n'
printf '[LOONAR] 영상이 나오지 않으면 로버의 송신 대상 IP를 확인하세요.\n'
if [[ $RECORD == 0 && $COMPASS == 0 ]]; then
    exec ffplay -hide_banner -loglevel warning -fflags nobuffer -flags low_delay \
        -framedrop -probesize 32 -analyzeduration 0 "${VIDEO_FILTER[@]}" udp://@:5600
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    show_error "녹화/방위 표시에는 ffmpeg 패키지가 필요합니다."
    exit 1
fi
PLAYER=(ffplay -hide_banner -loglevel warning -fflags nobuffer -flags low_delay
        -framedrop -probesize 32 -analyzeduration 0 "${VIDEO_FILTER[@]}" -i pipe:0)
if [[ $COMPASS == 1 ]]; then
    if ! /usr/bin/python3 -c 'import tkinter; from PIL import Image, ImageTk' 2>/dev/null; then
        show_error "방위 표시: sudo apt install python3-tk python3-pil python3-pil.imagetk"
        exit 1
    fi
    export PYTHONPATH="$GCS_ROOT${PYTHONPATH:+:$PYTHONPATH}"
    PLAYER=(/usr/bin/python3 -m cli.video_compass)
    if [[ $ROTATE_LEFT == 1 ]]; then PLAYER+=(--rotate-left); fi
fi
RECORD_OUTPUT=()
if [[ $RECORD == 1 ]]; then
    RECORD_DIR=${LOONAR_VIDEO_DIR:-"$HOME/Videos/LOONAR"}
    mkdir -p -- "$RECORD_DIR"
    RECORD_PATH="$RECORD_DIR/camera_$(date +%Y%m%d_%H%M%S_%N).ts"
    RECORD_OUTPUT=(-map 0:v:0 -c:v copy -f mpegts "$RECORD_PATH")
    printf '[LOONAR] 녹화 파일: %s\n' "$RECORD_PATH"
fi
PREVIEW_DIR=$(mktemp -d "$RUNTIME_DIR/video-preview.XXXXXX")
RECORDER_PID=
PLAYER_PID=
cleanup() {
    trap - EXIT INT TERM HUP
    for pid in "$RECORDER_PID" "$PLAYER_PID"; do
        if [[ -n $pid ]]; then kill -TERM "$pid" 2>/dev/null || true; fi
    done
    for pid in "$RECORDER_PID" "$PLAYER_PID"; do
        if [[ -n $pid ]]; then wait "$pid" 2>/dev/null || true; fi
    done
    rm -f -- "$PREVIEW_DIR/stream.ts"
    rmdir -- "$PREVIEW_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
mkfifo "$PREVIEW_DIR/stream.ts"
printf '[LOONAR] 영상 창을 닫거나 Ctrl+C를 누르면 녹화가 종료됩니다.\n'
# One UDP receiver; copy the encoded video to disk and the local preview.
# MPEG-TS stays readable without the finalization required by ordinary MP4.
ffmpeg -hide_banner -loglevel warning -nostdin -n \
    -probesize 32768 -analyzeduration 100000 \
    -i 'udp://@:5600?fifo_size=8192&overrun_nonfatal=1' \
    "${RECORD_OUTPUT[@]}" \
    -map 0:v:0 -c:v copy -f mpegts -flush_packets 1 pipe:1 \
    > "$PREVIEW_DIR/stream.ts" &
RECORDER_PID=$!
"${PLAYER[@]}" < "$PREVIEW_DIR/stream.ts" &
PLAYER_PID=$!
# Stop the other child as soon as either recording or preview exits.
wait -n "$RECORDER_PID" "$PLAYER_PID"
