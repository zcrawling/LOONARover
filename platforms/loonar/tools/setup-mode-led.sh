#!/usr/bin/env bash
# Pi-side installer. PIO setup must already have been completed.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID == 0 ]]; then
    echo 'Run as the normal Pi user; system installation uses sudo.' >&2
    exit 1
fi
python3 "$HERE/neopixel.py" --check
python_path="$HOME/.venvs/loonar-neopixel/bin/python"
python3 - "$HERE" "$python_path" "$(id -un)" "$(id -gn)" <<'PY' | sudo tee /etc/systemd/system/loonar-mode-led.service >/dev/null
from pathlib import Path
import sys
folder, python, user, group = sys.argv[1:]
text = (Path(folder)/'neopixel-pio/loonar-mode-led.service.in').read_text()
# Quote paths for systemd ExecStart, including literal % and shell-independent escaping.
def quote(value):
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
for key, value in {'USER':user,'GROUP':group,'PYTHON':quote(python),
                   'SCRIPT':quote(str(Path(folder)/'mode_led.py'))}.items():
    text = text.replace('@'+key+'@', value)
print(text)
PY
sudo systemctl daemon-reload
sudo systemctl enable --now loonar-mode-led.service
sudo systemctl restart loonar-mode-led.service
sudo systemctl status --no-pager loonar-mode-led.service
