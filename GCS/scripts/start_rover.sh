#!/usr/bin/env bash

set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

LAST_TARGET_FILE="$RUNTIME_DIR/last_ssh_target"
DEFAULT_TARGET="rover@192.168.1.50"
[[ -s $LAST_TARGET_FILE ]] && DEFAULT_TARGET=$(<"$LAST_TARGET_FILE")

TARGET=$(prompt_text "LOONAR 로버 실행" \
    "SSH 접속 주소를 입력하세요. 예: rover@192.168.1.50" "$DEFAULT_TARGET") || exit 0
if ! valid_ssh_target "$TARGET"; then
    show_error "주소 형식이 올바르지 않습니다. rover@192.168.1.50 형식으로 입력하세요."
    exit 1
fi
printf '%s\n' "$TARGET" > "$LAST_TARGET_FILE"

printf '\n[LOONAR] %s에 접속합니다. SSH 암호를 입력하세요.\n\n' "$TARGET"

CONTROL_SOCKET="$RUNTIME_DIR/ssh-control-${TARGET//@/_}"
rm -f "$CONTROL_SOCKET"

close_master() {
    ssh -S "$CONTROL_SOCKET" -O exit "$TARGET" >/dev/null 2>&1 || true
    rm -f "$CONTROL_SOCKET"
}
trap close_master EXIT INT TERM

# Authenticate once, then reuse this SSH connection for setup and the shell.
if ! ssh -M -S "$CONTROL_SOCKET" -o ControlPersist=600 \
    -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 \
    -fnNT "$TARGET"; then
    show_error "로버 SSH 연결에 실패했습니다. 주소와 암호를 확인하세요."
    exit 1
fi

set +e
REMOTE_CODE=$(base64 -w 0 "$GCS_ROOT/scripts/rover_start_remote.sh")
REMOTE_COMMAND="stty -echo; bash -c \"\$(printf '%s' '$REMOTE_CODE' | base64 -d)\"; status=\$?; stty echo; exit \$status"
ssh -tt \
    -S "$CONTROL_SOCKET" \
    "$TARGET" "$REMOTE_COMMAND"

status=$?
set -e
if [[ $status -ne 0 ]]; then
    printf '\n로버 준비에 실패했습니다.\n'
    printf '엔터를 누르면 창을 닫습니다.'
    read -r _ || true
    exit "$status"
fi

printf '[LOONAR] 로버 SSH 접속을 유지합니다. 끝내려면 exit를 입력하세요.\n\n'
set +e
ssh -tt -S "$CONTROL_SOCKET" "$TARGET"
status=$?
set -e
printf '\nSSH 연결이 종료되었습니다. 엔터를 누르면 창을 닫습니다.'
read -r _ || true
exit "$status"
