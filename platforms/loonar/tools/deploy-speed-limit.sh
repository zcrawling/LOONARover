#!/usr/bin/env bash
# Run on the development PC. Does not restart services or send motion.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
TARGET=${1:-loonar@192.168.0.14}
ssh -o ConnectTimeout=5 "$TARGET" 'set -eu
base="$HOME/LOONAR/platforms/loonar/tools/mcu_v2"
backup="$HOME/loonar-motor-bench/speed-limit-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup" "$HOME/loonar-motor-bench/speed-limit-stage"
cp "$base/config.py" "$base/backend.py" "$backup/"
printf "Backup: %s\n" "$backup"'
scp "$ROOT/platforms/loonar/tools/mcu_v2/"{config,backend,test_speed_limit}.py \
  "$TARGET:loonar-motor-bench/speed-limit-stage/"
ssh "$TARGET" 'set -eu
stage="$HOME/loonar-motor-bench/speed-limit-stage"
base="$HOME/LOONAR/platforms/loonar/tools/mcu_v2"
python3 -m py_compile "$stage/config.py" "$stage/backend.py" "$stage/test_speed_limit.py"
cp "$stage/config.py" "$stage/backend.py" "$stage/test_speed_limit.py" "$base/"
PYTHONPATH="$HOME/LOONAR/platforms/loonar/tools" python3 -m unittest mcu_v2.test_speed_limit
PYTHONPATH="$HOME/LOONAR/platforms/loonar/tools" python3 -m mcu_v2.backend --help >/dev/null
printf "Deployed +/-0.4 m/s, +/-3.8 rad/s and combined wheel-speed normalization. Restart ground-support to activate.\n"'
