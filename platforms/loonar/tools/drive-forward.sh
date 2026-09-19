#!/usr/bin/env bash
# User-run continuous 0.03 m/s command through the existing vehicle gateway.
set -euo pipefail

CTL="${VEHICLE_GATEWAYCTL:-/opt/loonar/current/bin/vehicle_gatewayctl}"
SOCK="${1:-$HOME/loonar-motor-bench/runtime/gateway/cfs.sock}"
child=''

if [[ ! -x "$CTL" ]]; then
  echo "Gateway command executable not found: $CTL" >&2
  exit 1
fi
if [[ ! -S "$SOCK" ]]; then
  echo "Gateway socket not found; start motor_bench first: $SOCK" >&2
  exit 1
fi

cleanup() {
  local result=$?
  trap - EXIT
  trap '' INT TERM HUP
  # Finish the command sender before STOP so no later motion overwrites it.
  if [[ -n "$child" ]]; then
    kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
  fi
  if "$CTL" stop "$SOCK"; then
    echo '정지 명령을 게이트웨이에 전송했습니다.'
  else
    echo '정지 명령 전송 실패: 게이트웨이 연결을 확인하세요.' >&2
    result=1
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

echo '선속도 0.03 m/s, 각속도 0 rad/s. Ctrl+C로 정지합니다.'
while true; do
  # The existing CLI refreshes the motion command every 50 ms.
  "$CTL" manual "$SOCK" 0.03 0 1000 &
  child=$!
  wait "$child"
  child=''
done
