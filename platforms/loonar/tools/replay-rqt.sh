#!/usr/bin/env bash
# Native laptop rqt, separate from existing dock layouts and Homebrew Python.
set -eo pipefail
TOOLS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MODE=${1:-current}
case "$MODE" in
  current|speed|pwm|voltage|topics|image) ;;
  *) echo "Usage: bash replay-rqt.sh [current|speed|pwm|voltage|topics|image]" >&2; exit 2 ;;
esac
unset PYTHONPATH LD_LIBRARY_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH
unset ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
source /opt/ros/lyrical/setup.bash
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-173}
export PYTHONNOUSERSITE=1
export QT_QPA_PLATFORM=${LOONAR_RQT_PLATFORM:-xcb}
export QT_STYLE_OVERRIDE=Fusion
export QT_SCALE_FACTOR=${LOONAR_RQT_SCALE:-1}
export QT_AUTO_SCREEN_SCALE_FACTOR=0
unset QT_SCREEN_SCALE_FACTORS
# Each mode gets independent geometry/settings; preserve the user's original rqt config.
export XDG_CONFIG_HOME="$HOME/.config/loonar-rqt/$MODE"
mkdir -p "$XDG_CONFIG_HOME"
RQT=(/usr/bin/python3 "$TOOLS/rqt_native_window.py")
if [[ "$MODE" == topics ]]; then
  exec "${RQT[@]}" --standalone rqt_topic.topic.Topic
elif [[ "$MODE" == image ]]; then
  exec "${RQT[@]}" --standalone rqt_image_view/ImageView
fi
PREFIX="/loonar_replay/view_$$"
case "$MODE" in
  current) FIELDS=("$PREFIX/current_a/data[0]" "$PREFIX/current_a/data[1]") ;;
  speed) FIELDS=("$PREFIX/speed_qpps/data[0]" "$PREFIX/speed_qpps/data[1]"
                 "$PREFIX/command_qpps/data[0]" "$PREFIX/command_qpps/data[1]") ;;
  pwm) FIELDS=("$PREFIX/pwm_raw/data[0]" "$PREFIX/pwm_raw/data[1]") ;;
  voltage) FIELDS=("$PREFIX/voltage_v/data[0]") ;;
esac
# Per-window topics allow independent graph windows to start and close safely.
/usr/bin/python3 "$TOOLS/rqt_motor_values.py" --ros-args -p "display_prefix:=$PREFIX" &
BRIDGE_PID=$!
cleanup() {
  if [[ -n "$BRIDGE_PID" ]]; then
    kill -INT "$BRIDGE_PID" 2>/dev/null || true
    wait "$BRIDGE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"${RQT[@]}" --standalone rqt_plot.plot.Plot --args "${FIELDS[@]}"
