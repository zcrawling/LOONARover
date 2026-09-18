#!/usr/bin/env bash
# Compile only: never open the camera or run the helper.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
SDK=${LOONAR_CUBEEYE_SDK:-$HOME/loonar-staging/cubeeye/arm64-pi5-linux-ubuntu_24_04/release}
mkdir -p "$ROOT/build/loonar"
python3 - "$ROOT" "$SDK" <<'PY'
from pathlib import Path
import os, subprocess, sys
root, sdk = map(Path, sys.argv[1:])
dirs = [sdk/'lib', sdk/'thirdparty/liblive555/lib/Release',
        *[d for d in (sdk/'thirdparty').glob('*/lib') if d.parent.name != 'python']]
env = dict(os.environ, LD_LIBRARY_PATH=':'.join(map(str, dirs)))
subprocess.run(['g++', '-std=c++17', '-O2', '-pthread',
    str(root/'tools/cubeeye_ros/capture_xyz.cpp'), '-I'+str(sdk/'include/CubeEye'),
    '-L'+str(sdk/'lib'), '-lCubeEye', *['-Wl,-rpath-link,'+str(d) for d in dirs],
    '-o', str(root/'build/loonar/capture_xyz')], env=env, check=True)
PY
