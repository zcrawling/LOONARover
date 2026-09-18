#!/usr/bin/env bash
# Native build only. No device enumeration, capture, or test commands.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
WORK=${LOONAR_CAMERA_BUILD_DIR:-$ROOT/build/pi-camera}
PREFIX=${LOONAR_CAMERA_PREFIX:-/opt/loonar/camera-stack/libcamera-0.7.2-rpt20260817-rpicam-1.13.0}
JOBS=${LOONAR_BUILD_JOBS:-2}
[[ $(uname -m) == aarch64 ]] || { echo "Build on the ARM64 Pi." >&2; exit 2; }
mkdir -p "$WORK"
checkout() {
  local name=$1 url=$2 tag=$3 revision=$4
  if [[ ! -d $WORK/$name/.git ]]; then
    git clone --depth 1 --branch "$tag" "$url" "$WORK/$name"
  fi
  [[ $(git -C "$WORK/$name" rev-parse HEAD) == "$revision" ]] || {
    echo "Unexpected $name revision; use a separate build directory." >&2; exit 2;
  }
  [[ -z $(git -C "$WORK/$name" status --porcelain --untracked-files=no) ]] || {
    echo "Modified $name source; refusing to build an unrecorded revision." >&2; exit 2;
  }
}
checkout libcamera https://github.com/raspberrypi/libcamera.git v0.7.2+rpt20260817 \
  6c1dd9d55573010f710c9e190a73e7e76f0d9432
checkout rpicam-apps https://github.com/raspberrypi/rpicam-apps.git v1.13.0 \
  6fcb0a3810715d05f01e06acb5f8e18e7d3a29cd

setup_args=()
[[ ! -f $WORK/libcamera/build/meson-private/coredata.dat ]] || setup_args+=(--reconfigure)
meson setup "${setup_args[@]}" "$WORK/libcamera/build" "$WORK/libcamera" \
  --prefix "$PREFIX" --libdir lib --buildtype release \
  -Dpipelines=rpi/pisp,rpi/vc4 -Dipas=rpi/pisp,rpi/vc4 \
  -Dgstreamer=enabled -Dcam=enabled -Dqcam=disabled -Dpycamera=disabled \
  -Dtest=false -Dlc-compliance=disabled -Ddocumentation=disabled
ninja -C "$WORK/libcamera/build" -j "$JOBS"
DESTDIR="$WORK/stage" meson install -C "$WORK/libcamera/build" --no-rebuild

# Build rpicam against the staged libcamera, without replacing distro libraries.
mkdir -p "$WORK/pkgconfig"
python3 - "$WORK/stage$PREFIX/lib/pkgconfig" "$WORK/pkgconfig" "$PREFIX" "$WORK/stage$PREFIX" <<'PY'
from pathlib import Path
import re, sys
source, output, prefix, staged = sys.argv[1:]
for pc in Path(source).glob('*.pc'):
    text = pc.read_text().replace(prefix, staged)
    text = re.sub(r'^prefix=.*$', 'prefix=' + staged, text, flags=re.M)
    (Path(output) / pc.name).write_text(text)
PY
export PKG_CONFIG_PATH="$WORK/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$WORK/stage$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
setup_args=()
[[ ! -f $WORK/rpicam-apps/build/meson-private/coredata.dat ]] || setup_args+=(--reconfigure)
# rpicam 1.13's libav encoder requires newer FFmpeg than Noble provides.
# Still capture remains available; video uses our separate GStreamer/x264 pipeline.
meson setup "${setup_args[@]}" "$WORK/rpicam-apps/build" "$WORK/rpicam-apps" \
  --prefix "$PREFIX" --libdir lib --buildtype release \
  -Denable_libav=disabled -Denable_drm=disabled -Denable_egl=disabled \
  -Denable_wayland=disabled -Denable_qt=disabled -Denable_opencv=disabled \
  -Denable_tflite=disabled -Denable_hailo=disabled -Denable_imx500=false
ninja -C "$WORK/rpicam-apps/build" -j "$JOBS"
DESTDIR="$WORK/stage" meson install -C "$WORK/rpicam-apps/build" --no-rebuild
printf '%s\n' "$PREFIX" > "$WORK/prefix.txt"
echo "Camera binaries staged at $WORK/stage$PREFIX. Nothing was captured or started."
