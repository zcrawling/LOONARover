#!/usr/bin/env bash
# Install prepared artifacts. Never enable or start any rover service.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 2; }
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
DEPLOY=$ROOT/platforms/loonar/deploy
RELEASE=${1:?Usage: install-runtime.sh RELEASE_ID}
[[ $RELEASE =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
DEST=/opt/loonar/releases/$RELEASE
ROS_INSTALL=${LOONAR_ROS_INSTALL:-/home/loonar/loonar_jazzy_ws/install}
SDK=${LOONAR_CUBEEYE_SDK:-/home/loonar/loonar-staging/cubeeye/arm64-pi5-linux-ubuntu_24_04/release}
CPU=$ROOT/build/gcs-test/cFS/build-native_std/exe/cpu1
HOST=$ROOT/build/gcs-test/host
CAM_WORK=$ROOT/build/pi-camera
CAM_PREFIX=$(cat "$CAM_WORK/prefix.txt")
[[ $CAM_PREFIX == /opt/loonar/camera-stack/* && $CAM_PREFIX != *..* ]] || exit 2
[[ ! -e $DEST ]] || { echo "Release already exists: $DEST" >&2; exit 2; }
id loonar >/dev/null
for file in "$CPU/core-cpu1" "$HOST/common/vehicle_gateway/vehicle_gatewayd" \
  "$HOST/common/vehicle_gateway/vehicle_gatewayctl" "$ROOT/build/loonar/capture_xyz" \
  "$ROS_INSTALL/setup.bash" "$CAM_WORK/stage$CAM_PREFIX/bin/rpicam-hello"; do
  [[ -f $file ]] || { echo "Missing artifact: $file" >&2; exit 2; }
done
for unit in vehicle_gatewayd loonar-cfs loonar-localization loonar-video loonar-tof; do
  if systemctl is-active --quiet "$unit.service"; then
    echo "$unit is active; this preparation installer requires an inactive stack." >&2; exit 2
  fi
done
for group in dialout video render plugdev; do
  getent group "$group" >/dev/null || groupadd --system "$group"
  usermod -aG "$group" loonar
done
install -d "$DEST/bin" "$DEST/lib/cubeeye" "$DEST/ros/install" "$DEST/cfs" \
  /etc/loonar /opt/loonar/vendor/cubeeye/2.5.9/release "$CAM_PREFIX"
install -m 755 "$HOST/common/vehicle_gateway/vehicle_gatewayd" \
  "$HOST/common/vehicle_gateway/vehicle_gatewayctl" "$ROOT/build/loonar/capture_xyz" "$DEST/bin/"
cp -a "$CPU/." "$DEST/cfs/"
cp -a "$ROS_INSTALL/." "$DEST/ros/install/"
cp -a "$SDK/." /opt/loonar/vendor/cubeeye/2.5.9/release/
cp -a "$CAM_WORK/stage$CAM_PREFIX/." "$CAM_PREFIX/"
install -m 755 "$DEPLOY"/run-*.sh "$DEPLOY/loonar-camera" "$DEPLOY/loonar-camera-env.sh" "$DEST/lib/"
install -m 755 "$ROOT/common/video/loonar-video-stream" "$DEST/lib/"
install -m 644 "$ROOT/tools/cubeeye_ros/bridge.py" "$DEST/lib/cubeeye/"
install -m 644 "$DEPLOY"/*.env.example /etc/loonar/
if [[ ! -e /etc/loonar/video.env ]]; then
  cat > /etc/loonar/video.env <<'EOF'
# Development computer address observed during preparation; change for another GCS.
GROUND_STATION_IP=10.42.0.1
VIDEO_PORT=5600
VIDEO_SOURCE=libcamera
VIDEO_PROFILE=low
VIDEO_ENCODER_THREADS=1
EOF
fi
if [[ ! -e /etc/loonar/ros.env ]]; then
  printf 'ROS_DOMAIN_ID=0\n' > /etc/loonar/ros.env
fi
# cFS writes files relative to its working directory. Preserve existing state.
install -d -o loonar -g loonar /var/lib/loonar/cfs
if [[ ! -e /var/lib/loonar/cfs/cf ]]; then
  cp -a "$CPU/cf" /var/lib/loonar/cfs/
  chown -R loonar:loonar /var/lib/loonar/cfs/cf
fi
chown -R root:root "$DEST" "$CAM_PREFIX" /opt/loonar/vendor/cubeeye/2.5.9
ln -sfn "$CAM_PREFIX" /opt/loonar/camera-stack/current
ln -sfn "$DEST" /opt/loonar/current
ln -sfn /opt/loonar/current/lib/loonar-camera /usr/local/bin/loonar-camera
install -m 644 "$DEPLOY/99-loonar-usb.rules" /etc/udev/rules.d/
install -m 644 "$ROOT/platforms/loonar/systemd/"* /etc/systemd/system/
udevadm control --reload-rules
systemctl daemon-reload
echo "Installed $DEST. Services were not enabled or started; no devices were opened."
