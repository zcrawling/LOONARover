#!/usr/bin/env bash
# Controlled LIMO acceptance-test harness.  Default mode is non-moving.
set -euo pipefail

WORKSPACE="${LOONAR_WORKSPACE:-/home/wego/loonar_ws}"
AGILEX_WORKSPACE="${AGILEX_WORKSPACE:-/home/wego/agilex_ws}"
RUNTIME_DIR="${LOONAR_RUNTIME_DIR:-/tmp/loonar-gateway-live-$UID}"
PORT_NAME="${LIMO_PORT_NAME:-ttylimo}"
LINEAR_MPS="0.05"
ANGULAR_RADPS="0.0"
DURATION_MS="1000"
START_BASE=0
MOVE=0
GATEWAY_PID=""
BACKEND_PID=""
BASE_PID=""

usage() {
  cat <<'EOF'
Usage: live_gateway_test.sh [--start-base] [--move] [--linear MPS] [--angular RADPS] [--duration MS]

Without --move, starts the Gateway and LIMO backend, confirms their connection
and the live manufacturer status topic, then exits without sending a non-zero command. With --move,
the supplied linear, angular, and duration values are passed to the Gateway
unchanged.

--start-base starts the vendor limo_base launch process with port_name:=ttylimo.
Omit it when the vendor driver is already running.
EOF
}

while (($#)); do
  case "$1" in
    --start-base) START_BASE=1 ;;
    --move) MOVE=1 ;;
    --linear) LINEAR_MPS="$2"; shift ;;
    --angular) ANGULAR_RADPS="$2"; shift ;;
    --duration) DURATION_MS="$2"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cleanup() {
  set +e
  [[ -n "$BACKEND_PID" ]] && kill -- "-$BACKEND_PID" 2>/dev/null
  [[ -n "$GATEWAY_PID" ]] && kill -- "-$GATEWAY_PID" 2>/dev/null
  [[ -n "$BASE_PID" ]] && kill -- "-$BASE_PID" 2>/dev/null
  wait ${BACKEND_PID#-} ${GATEWAY_PID#-} ${BASE_PID#-} 2>/dev/null
  rm -rf "$RUNTIME_DIR"
}
trap cleanup EXIT INT TERM

# ROS Humble setup scripts dereference optional AMENT_* variables.  They must
# be sourced with nounset disabled, then this harness restores strict mode.
set +u
source /opt/ros/humble/setup.bash
source "$AGILEX_WORKSPACE/install/setup.bash"
source "$WORKSPACE/install/setup.bash"
set -u

require() { command -v "$1" >/dev/null || { echo "missing command: $1" >&2; exit 1; }; }
for command in ros2 setsid; do require "$command"; done
[[ -x "$WORKSPACE/build/gateway/vehicle_gatewayd" ]] || { echo "Gateway not built: $WORKSPACE/build/gateway" >&2; exit 1; }
[[ -x "$WORKSPACE/build/gateway/vehicle_gatewayctl" ]] || { echo "Gateway control tool not built" >&2; exit 1; }
[[ -e "/dev/$PORT_NAME" ]] || { echo "missing /dev/$PORT_NAME; install/verify the udev alias first" >&2; exit 1; }

rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"

if ((START_BASE)); then
  setsid ros2 launch limo_base limo_base.launch.py "port_name:=$PORT_NAME" >"$RUNTIME_DIR/limo_base.log" 2>&1 &
  BASE_PID="$!"
fi

setsid "$WORKSPACE/build/gateway/vehicle_gatewayd" --runtime-dir "$RUNTIME_DIR" >"$RUNTIME_DIR/gateway.log" 2>&1 &
GATEWAY_PID="$!"
for _ in $(seq 1 30); do [[ -S "$RUNTIME_DIR/backend.sock" ]] && break; sleep 0.1; done
[[ -S "$RUNTIME_DIR/backend.sock" ]] || { echo "Gateway did not create backend.sock" >&2; exit 1; }

setsid ros2 run loonar_limo_backend loonar_limo_backend --ros-args \
  -p "gateway_socket:=$RUNTIME_DIR/backend.sock" >"$RUNTIME_DIR/limo_backend.log" 2>&1 &
BACKEND_PID="$!"

echo "Waiting for /limo_status (manufacturer-driver connectivity diagnostic)..."
LIMO_STATUS="$(timeout 10s ros2 topic echo --once /limo_status)" || {
  echo "No /limo_status. Check vendor driver, /dev/$PORT_NAME, and $RUNTIME_DIR/limo_base.log" >&2
  exit 1
}
printf 'Live LIMO status:\n%s\n' "$LIMO_STATUS"
if grep -q '^control_mode: 0$' <<<"$LIMO_STATUS"; then
  echo "WARNING: LIMO reports control_mode=0 (Standby). Gateway packets can be sent, but the chassis may ignore motion." >&2
fi

echo "SMOKE PASS: Gateway, backend, and live LIMO status are connected. No non-zero command was sent."
if (( ! MOVE )); then exit 0; fi

echo "Sending MANUAL: linear=$LINEAR_MPS m/s angular=$ANGULAR_RADPS rad/s duration=$DURATION_MS ms."

"$WORKSPACE/build/gateway/vehicle_gatewayctl" manual "$RUNTIME_DIR/cfs.sock" \
  "$LINEAR_MPS" "$ANGULAR_RADPS" "$DURATION_MS"
"$WORKSPACE/build/gateway/vehicle_gatewayctl" stop "$RUNTIME_DIR/cfs.sock"
echo "COMMAND_SENT: explicit STOP was sent after the requested MANUAL interval."
