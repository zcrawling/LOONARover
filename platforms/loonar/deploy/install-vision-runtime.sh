#!/usr/bin/env bash
# Separate Pi CPU inference environment; no camera or rover service is started.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo on the Pi.' >&2; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'Use the ARM64 Raspberry Pi.' >&2; exit 2; }
# sudo does not retain the caller's ROS Python path. The rclpy import check
# below must run in the same ROS environment as run-vision.sh.
set +u
source /opt/ros/jazzy/setup.bash
set -u
VENV=/opt/loonar/vision-venv
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
MODEL_SOURCE=${1:-}
[[ $# -le 1 ]] || { echo 'Usage: install-vision-runtime.sh [MODEL_DIR]' >&2; exit 2; }
export YOLO_AUTOINSTALL=false
if [[ ! -e $VENV/bin/python ]]; then
  python3 -m venv --system-site-packages "$VENV"
fi
# Binary wheels only: do not compile torch/OpenCV/CUDA on the Pi.
# PyPI's newer ARM64 torch wheels pull CUDA dependencies. Install the CPU
# build explicitly and constrain later resolution so it cannot replace it.
TORCH_PACKAGES=('torch==2.8.0+cpu' 'torchvision==0.23.0')
"$VENV/bin/python" -m pip install --only-binary=:all: \
  --index-url https://download.pytorch.org/whl/cpu "${TORCH_PACKAGES[@]}"
VISION_PACKAGES=('ultralytics==8.4.145' 'ncnn==1.0.20260526'
  'numpy<2' 'opencv-python<4.12' "${TORCH_PACKAGES[@]}")
REPORT=$(mktemp)
trap 'rm -f -- "$REPORT"' EXIT
"$VENV/bin/python" -m pip install --dry-run --report "$REPORT" --only-binary=:all: \
  "${VISION_PACKAGES[@]}"
"$VENV/bin/python" - "$REPORT" <<'PY'
import importlib.metadata
import json
import sys
planned = [p['metadata']['name'] for p in json.load(open(sys.argv[1]))['install']]
present = [d.metadata['Name'] or '' for d in importlib.metadata.distributions()]
# Ultralytics depends on the small Python NVML binding even on CPU hosts.
# It does not ship CUDA libraries; allow that binding, not GPU runtimes.
bad = [n for n in planned + present if n.lower().replace('_', '-') != 'nvidia-ml-py'
       and n.lower().replace('_', '-').startswith(('nvidia-', 'cuda-', 'tensorrt'))]
if bad:
    raise SystemExit('CUDA/TensorRT dependencies rejected before installation: ' + ', '.join(bad))
PY
"$VENV/bin/python" -m pip install --only-binary=:all: "${VISION_PACKAGES[@]}"
"$VENV/bin/python" - <<'PY'
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstApp, GstVideo
import rclpy
import torch
import ultralytics
import ncnn
assert torch.version.cuda is None, 'Expected a CPU-only torch build'
print('Pi vision runtime:', 'torch', torch.__version__,
      'ultralytics', ultralytics.__version__, 'ncnn', ncnn.__version__,
      'CUDA available', torch.cuda.is_available())
PY
if "$VENV/bin/python" -m pip list --format=freeze | grep -Eiv '^nvidia-ml-py==' | grep -Eiq '^(nvidia-|cuda-|tensorrt)'; then
  echo 'Unexpected CUDA package in Pi vision environment.' >&2
  exit 1
fi
echo "Pi vision Python ready: $VENV/bin/python"
if [[ -n $MODEL_SOURCE ]]; then
  PYTHONPATH="$ROOT/common/ros2/loonar_target_vision${PYTHONPATH:+:$PYTHONPATH}" \
    "$VENV/bin/python" - "$MODEL_SOURCE" "$ROOT" <<'PY'
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import yaml
from loonar_target_vision.node import load_ncnn
from loonar_target_vision.contract import model_sha256

source, root = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
config_path = Path('/etc/loonar/vision.yaml')
template = root / 'common/ros2/loonar_target_vision/config/vision.yaml'
config = yaml.safe_load((config_path if config_path.exists() else template).read_text())
params = config['loonar_target_vision']['ros__parameters']
# Explicit MODEL_DIR authorizes changing only the vision model path and hash.
_, digest, _, mode = load_ncnn(source, int(params['input_height']), int(params['input_width']),
                              int(params['cpu_threads']))
base = Path('/var/lib/loonar/vision')
base.mkdir(parents=True, exist_ok=True)
destination = base / (digest + '_ncnn_model')
if destination.exists():
    if model_sha256(destination) != digest:
        raise ValueError('existing content-addressed model is damaged; nothing overwritten')
else:
    stage = Path(tempfile.mkdtemp(prefix='.install-', dir=base))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        if model_sha256(stage) != digest:
            raise ValueError('model changed during installation')
        for item in stage.rglob('*'):
            item.chmod(0o755 if item.is_dir() else 0o644)
        stage.chmod(0o755)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
params['model_path'], params['model_sha256'] = str(destination), digest
config_path.parent.mkdir(parents=True, exist_ok=True)
if config_path.exists():
    backup = config_path.with_name('vision.yaml.before-ncnn')
    if not backup.exists():
        shutil.copy2(config_path, backup)
fd, temp = tempfile.mkstemp(prefix='.vision-', suffix='.yaml', dir=config_path.parent)
try:
    with os.fdopen(fd, 'w') as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    os.chmod(temp, 0o644)
    os.replace(temp, config_path)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
print(json.dumps({'model': str(destination), 'sha256': digest, 'mode': mode}))
print('Model installed. No service was started or restarted.')
PY
else
  echo 'No model changed. Run again with an explicit *_ncnn_model directory to install a model.'
fi
