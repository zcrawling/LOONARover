#!/usr/bin/env bash

set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LAST_IP_FILE="$RUNTIME_DIR/last_rover_ip"
DEFAULT_IP="192.168.1.50"
if [[ -s $LAST_IP_FILE ]]; then
    DEFAULT_IP=$(<"$LAST_IP_FILE")
elif [[ -s $RUNTIME_DIR/last_ssh_target ]]; then
    DEFAULT_IP=$(<"$RUNTIME_DIR/last_ssh_target")
    DEFAULT_IP=${DEFAULT_IP#*@}
fi

if [[ $# -gt 1 ]]; then
    echo 'Usage: start_gcs.sh [ROVER_IP]' >&2
    exit 2
fi
if [[ $# -eq 1 ]]; then
    ROVER_IP=$1
else
    ROVER_IP=$(prompt_text "LOONAR 실시간 지상국" \
        "현재 로버 IP를 입력하세요. 예: 192.168.1.50" "$DEFAULT_IP") || exit 0
fi
if ! valid_host "$ROVER_IP"; then
    show_error "IP 또는 호스트 이름 형식이 올바르지 않습니다."
    exit 1
fi
printf '%s\n' "$ROVER_IP" > "$LAST_IP_FILE"

cd "$GCS_ROOT"
URL="http://127.0.0.1:8080"

printf '[LOONAR] 실제 로버 %s에 연결합니다.\n' "$ROVER_IP"
printf '[LOONAR] 브라우저 주소: %s\n' "$URL"

open_gcs_windows() {
    local video_options=()
    if [[ ${GCS_VIDEO_ROTATE_LEFT:-0} == 1 ]]; then
        video_options+=(--rotate-left)
    fi
    xdg-open "$URL" >/dev/null 2>&1 || true
    if ! command -v gnome-terminal >/dev/null 2>&1; then
        printf '[LOONAR] gnome-terminal이 없어 별도 창을 열지 못했습니다.\n' >&2
        return
    fi
    gnome-terminal -- "$GCS_ROOT/scripts/start_diagnostics.sh" --host "$ROVER_IP" \
        >/dev/null 2>&1 || printf '[LOONAR] 진단 창 열기 실패\n' >&2
    gnome-terminal -- "$GCS_ROOT/scripts/start_video.sh" "${video_options[@]}" \
        >/dev/null 2>&1 || printf '[LOONAR] 영상 창 열기 실패\n' >&2
}

RUNNING_SOURCE=$(python3 - "$URL/api/state" <<'PY' 2>/dev/null || true
import json, sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=0.5) as response:
    print(json.load(response).get("source", ""))
PY
)
if [[ -n $RUNNING_SOURCE ]]; then
    if [[ $RUNNING_SOURCE == "REAL ROVER / $ROVER_IP" ]]; then
        printf '[LOONAR] 같은 로버의 지상국이 이미 실행 중입니다. 기존 화면을 엽니다.\n'
        open_gcs_windows
        exit 0
    fi
    show_error "8080 포트에서 다른 지상국이 실행 중입니다: $RUNNING_SOURCE"
    exit 1
fi

python3 -B -m webui.server --real-host "$ROVER_IP" --config "${GCS_CONFIG:-$GCS_ROOT/config/gcs.toml}" &
SERVER_PID=$!
cleanup() {
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ready=0
for _ in {1..50}; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        wait "$SERVER_PID" || true
        show_error "지상국을 시작하지 못했습니다. 이 터미널의 오류를 확인하세요."
        printf '\n엔터를 누르면 창을 닫습니다.'
        read -r _ || true
        exit 1
    fi
    if python3 - "$URL/api/state" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=0.2).close()
PY
    then
        ready=1
        break
    fi
    sleep 0.2
done

if [[ $ready -eq 1 ]]; then
    open_gcs_windows
else
    show_error "지상국 화면이 제한 시간 안에 준비되지 않았습니다."
fi

printf '[LOONAR] 실행 중입니다. 종료하려면 Ctrl+C를 누르세요.\n'
wait "$SERVER_PID"
