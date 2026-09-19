#!/usr/bin/env bash
set -u

STATE_DIR="$HOME/.local/state/loonar"
mkdir -p "$STATE_DIR"

is_running() {
    pgrep -u "$USER" -f "$1" >/dev/null 2>&1
}

start_component() {
    local name=$1 pattern=$2 command=$3 readiness=$4 started=0
    if is_running "$pattern"; then
        printf '[확인 중] %s는 이미 실행 중입니다. 준비 상태를 확인합니다.\n' "$name"
    else
        printf '[시작 중] %s\n' "$name"
        nohup bash -lc "$command" >"$STATE_DIR/$name.log" 2>&1 </dev/null &
        started=1
    fi

    for _ in $(seq 1 20); do
        if is_running "$pattern" && bash -lc "$readiness" >/dev/null 2>&1; then
            if [[ $started -eq 1 ]]; then
                printf '[준비 완료] %s\n' "$name"
            else
                printf '[준비됨] %s\n' "$name"
            fi
            return 0
        fi
        sleep 1
    done

    printf '[준비 실패] %s — 로그: %s/%s.log\n' "$name" "$STATE_DIR" "$name"
    tail -n 12 "$STATE_DIR/$name.log" 2>/dev/null || true
    return 1
}

if ! start_component limo_base \
    '/limo_base/lib/limo_base/limo_base' \
    'source /opt/ros/humble/setup.bash; source "$HOME/agilex_ws/install/setup.bash"; exec ros2 launch limo_base limo_base.launch.py port_name:=ttylimo' \
    'source /opt/ros/humble/setup.bash; source "$HOME/agilex_ws/install/setup.bash"; ros2 topic list 2>/dev/null | grep -qx /limo_status'; then
    printf '\nlimo_base가 준비되지 않아 다음 단계를 실행하지 않습니다.\n'
    exit 1
fi

if ! start_component vehicle_gatewayd \
    '/vehicle_gatewayd( |$)' \
    'runtime="/tmp/loonar-gateway-$UID"; mkdir -p "$runtime"; exec "$HOME/loonar_ws/build/gateway/vehicle_gatewayd" --runtime-dir "$runtime"' \
    'runtime="/tmp/loonar-gateway-$UID"; test -S "$runtime/backend.sock" && test -S "$runtime/cfs.sock"'; then
    printf '\nvehicle_gatewayd가 준비되지 않아 다음 단계를 실행하지 않습니다.\n'
    exit 1
fi

if ! start_component loonar_limo_backend \
    '/loonar_limo_backend/lib/loonar_limo_backend' \
    'source /opt/ros/humble/setup.bash; source "$HOME/agilex_ws/install/setup.bash"; source "$HOME/loonar_ws/install/setup.bash"; exec ros2 run loonar_limo_backend loonar_limo_backend --ros-args -p "gateway_socket:=/tmp/loonar-gateway-$UID/backend.sock"' \
    'pgrep -u "$USER" -f "/loonar_limo_backend/lib/loonar_limo_backend" >/dev/null'; then
    printf '\nloonar_limo_backend가 준비되지 않아 다음 단계를 실행하지 않습니다.\n'
    exit 1
fi

if ! start_component core-cpu1 \
    '(^|/)core-cpu1( |$)' \
    'cd "$HOME/loonar_cfs/build-native_std/exe/cpu1"; export LOONAR_GATEWAY_SOCKET="/tmp/loonar-gateway-$UID/cfs.sock"; exec ./core-cpu1' \
    'ss -ltn 2>/dev/null | grep -qE "[:.]7443[[:space:]]"'; then
    printf '\ncore-cpu1이 준비되지 않았습니다.\n'
    exit 1
fi

GCS_IP=${SSH_CONNECTION%% *}
if [[ $GCS_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    current_ip=$(sed -n 's/^GROUND_STATION_IP=//p' /etc/loonar/video.env 2>/dev/null | head -n 1)
    if [[ $current_ip != "$GCS_IP" ]]; then
        printf '[영상 설정] 송신 목적지를 %s로 변경합니다. sudo 암호가 필요할 수 있습니다.\n' "$GCS_IP"
        sudo sed -i "s/^GROUND_STATION_IP=.*/GROUND_STATION_IP=$GCS_IP/" /etc/loonar/video.env || exit 1
        sudo systemctl restart loonar-video.service || exit 1
    elif ! systemctl is-active --quiet loonar-video.service; then
        printf '[영상 설정] 영상 송신 서비스를 시작합니다. sudo 암호가 필요할 수 있습니다.\n'
        sudo systemctl start loonar-video.service || exit 1
    fi
    printf '[영상 준비 완료] 로버 → %s:5600\n' "$GCS_IP"
else
    printf '[영상 준비 실패] SSH 연결에서 지상국 IPv4 주소를 확인할 수 없습니다.\n'
    exit 1
fi

printf '\n'
printf '로버 통신 구성요소 4개가 순서대로 준비되었습니다.\n'
printf '영상 송신도 준비되었습니다.\n'
printf '준비 작업을 마쳤습니다. 로버 SSH 터미널로 전환합니다.\n'
