#!/usr/bin/env bash

set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LAST_TARGET_FILE="$RUNTIME_DIR/last_ssh_target"
DEFAULT_TARGET="rover@192.168.1.50"
[[ -s $LAST_TARGET_FILE ]] && DEFAULT_TARGET=$(<"$LAST_TARGET_FILE")

if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
    zenity --question --title="LOONAR 로버 종료" \
        --text="로버를 정지하고 통신 프로그램 4개를 종료하시겠습니까?" \
        --ok-label="종료" --cancel-label="취소" 2>/dev/null || exit 0
fi

TARGET=$(prompt_text "LOONAR 로버 종료" \
    "종료할 로버의 SSH 주소를 입력하세요." "$DEFAULT_TARGET") || exit 0
if ! valid_ssh_target "$TARGET"; then
    show_error "주소 형식이 올바르지 않습니다. rover@192.168.1.50 형식으로 입력하세요."
    exit 1
fi
printf '%s\n' "$TARGET" > "$LAST_TARGET_FILE"

printf '\n[LOONAR] %s에 접속합니다. SSH 암호를 입력하세요.\n\n' "$TARGET"

ssh -o ConnectTimeout=8 "$TARGET" 'bash -s' <<'REMOTE_SCRIPT'
set -u

if [[ -f /opt/ros/humble/setup.bash ]]; then
    source /opt/ros/humble/setup.bash
    [[ -f "$HOME/agilex_ws/install/setup.bash" ]] && source "$HOME/agilex_ws/install/setup.bash"
    timeout 3 ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
        '{linear: {x: 0.0}, angular: {z: 0.0}}' >/dev/null 2>&1 || true
    printf '[정지 명령] 속도 0을 전달했습니다.\n'
fi

stop_pattern() {
    local name=$1 pattern=$2
    if ! pgrep -u "$USER" -f "$pattern" >/dev/null 2>&1; then
        printf '[이미 종료됨] %s\n' "$name"
        return 0
    fi
    pkill -u "$USER" -TERM -f "$pattern" 2>/dev/null || true
    for _ in $(seq 1 10); do
        if ! pgrep -u "$USER" -f "$pattern" >/dev/null 2>&1; then
            printf '[종료 완료] %s\n' "$name"
            return 0
        fi
        sleep 1
    done
    pkill -u "$USER" -KILL -f "$pattern" 2>/dev/null || true
    sleep 1
    if pgrep -u "$USER" -f "$pattern" >/dev/null 2>&1; then
        printf '[종료 실패] %s\n' "$name"
        return 1
    fi
    printf '[강제 종료 완료] %s\n' "$name"
}

failed=0
stop_pattern core-cpu1 '(^|/)core-cpu1( |$)' || failed=1
stop_pattern loonar_limo_backend '/loonar_limo_backend/lib/loonar_limo_backend' || failed=1
stop_pattern loonar_limo_backend_launcher 'ros2 run loonar_limo_backend' || failed=1
stop_pattern vehicle_gatewayd '/vehicle_gatewayd( |$)' || failed=1
stop_pattern limo_base '/limo_base/lib/limo_base/limo_base' || failed=1
stop_pattern limo_base_launcher 'ros2 launch limo_base' || failed=1

printf '\n'
if [[ $failed -eq 0 ]]; then
    printf '로버 통신 프로그램 4개가 모두 종료되었습니다.\n'
else
    printf '일부 프로그램을 종료하지 못했습니다. 위 결과를 확인하세요.\n'
fi
exit "$failed"
REMOTE_SCRIPT

status=$?
printf '\n엔터를 누르면 창을 닫습니다.'
read -r _ || true
exit "$status"
