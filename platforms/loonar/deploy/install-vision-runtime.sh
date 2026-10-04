#!/usr/bin/env bash
# Separate Pi CPU inference environment; no camera or rover service is started.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo on the Pi.' >&2; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'Use the ARM64 Raspberry Pi.' >&2; exit 2; }
VENV=/opt/loonar/vision-venv
if [[ ! -e $VENV/bin/python ]]; then
  python3 -m venv --system-site-packages "$VENV"
fi
# Binary wheels only: do not compile torch/OpenCV/CUDA on the Pi.
"$VENV/bin/python" -m pip install --only-binary=:all: 'ultralytics==8.4.145'
"$VENV/bin/python" - <<'PY'
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstApp, GstVideo
import rclpy
import torch
import ultralytics
print('Pi vision runtime:', 'torch', torch.__version__,
      'ultralytics', ultralytics.__version__, 'CUDA available', torch.cuda.is_available())
PY
if "$VENV/bin/python" -m pip list --format=freeze | grep -Eiq '^(nvidia-|cuda-)'; then
  echo 'Unexpected CUDA package in Pi vision environment.' >&2
  exit 1
fi
echo "Pi vision Python ready: $VENV/bin/python"
