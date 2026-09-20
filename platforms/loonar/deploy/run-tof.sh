#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
if [[ -f /etc/loonar/ros.env ]]; then
  set -a
  source /etc/loonar/ros.env
  set +a
fi
source /etc/loonar/tof.env
# Never silently use LIMO's mounting geometry on the final rover.
case "${TOF_PUBLISH_BASE_TF:-true}" in
false) MOUNT_ARGS=(--no-base-tf) ;;
true)
: "${TOF_X_M:?Set the measured ToF mount}"
: "${TOF_Y_M:?Set the measured ToF mount}"
: "${TOF_Z_M:?Set the measured ToF mount}"
: "${TOF_ROLL_RAD:?Set the measured ToF mount}"
: "${TOF_PITCH_RAD:?Set the measured ToF mount}"
: "${TOF_YAW_RAD:?Set the measured ToF mount}"
MOUNT_ARGS=(--x "$TOF_X_M" --y "$TOF_Y_M" --z "$TOF_Z_M"
  --roll "$TOF_ROLL_RAD" --pitch "$TOF_PITCH_RAD" --yaw "$TOF_YAW_RAD") ;;
*) echo 'TOF_PUBLISH_BASE_TF must be true or false' >&2; exit 2 ;;
esac
exec /usr/bin/python3 /opt/loonar/current/lib/cubeeye/bridge.py \
  --sdk /opt/loonar/vendor/cubeeye/2.5.9/release \
  --helper /opt/loonar/current/bin/capture_xyz \
  --reliable \
  --hz "${TOF_HZ:-5}" --stride "${TOF_STRIDE:-4}" \
  "${MOUNT_ARGS[@]}"
