#!/usr/bin/env bash
# Install Pi5 GPIO22 NeoPixel support on Ubuntu 6.8; no reboot or kernel replacement.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
release=$(uname -r)
if [[ $release != 6.8.*-raspi ]] || ! grep -aq 'Raspberry Pi 5' /proc/device-tree/model; then
    echo 'This installer targets Raspberry Pi 5 / Ubuntu 6.8.x-raspi only.' >&2
    exit 1
fi
if [[ $EUID == 0 ]]; then
    echo 'Run as the regular Pi user; individual system installation steps use sudo.' >&2
    exit 1
fi
build_dir="${XDG_CACHE_HOME:-$HOME/.cache}/loonar-neopixel/$release"
venv_dir="$HOME/.venvs/loonar-neopixel"
sudo apt-get install -y "linux-headers-$release" build-essential device-tree-compiler python3-venv
python3 "$HERE/neopixel-pio/build_driver.py" "$build_dir"
# Fragment context cannot express the target PCI parent's 3-cell addresses to dtc.
# The overlay adds the already assigned SRAM BAR and preserves the register BAR.
dtc -@ -Wno-ranges_format -Wno-unit_address_vs_reg -Wno-avoid_default_addr_size \
    -I dts -O dtb -o "$build_dir/loonar-rp1-pio.dtbo" "$HERE/neopixel-pio/loonar-rp1-pio.dts"
module_dir="/lib/modules/$release/updates/loonar-neopixel"
resource_dir=/usr/local/lib/loonar-neopixel
sudo install -d "$module_dir" "$resource_dir"
sudo install -m 0644 "$build_dir/"{rp1-mailbox,rp1-fw,rp1-pio}.ko "$module_dir/"
sudo depmod -a "$release"
sudo install -m 0644 "$build_dir/loonar-rp1-pio.dtbo" "$build_dir/source-manifest.json" "$resource_dir/"
sudo install -m 0755 "$HERE/neopixel-pio/activate.sh" "$resource_dir/activate.sh"
printf '%s\n' "$release" | sudo tee "$resource_dir/kernel-release" >/dev/null
sudo install -m 0644 "$HERE/neopixel-pio/loonar-neopixel-pio.service" /etc/systemd/system/
# Restrict device access to this account's existing primary group.
printf 'SUBSYSTEM=="rp1-pio", KERNEL=="pio0", GROUP="%s", MODE="0660"\n' "$(id -gn)" \
    | sudo tee /etc/udev/rules.d/70-loonar-neopixel-pio.rules >/dev/null
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo systemctl enable --now loonar-neopixel-pio.service
sudo udevadm trigger --action=change /sys/class/rp1-pio/pio0
sudo udevadm settle
python3 -m venv "$venv_dir"
"$venv_dir/bin/pip" install 'Adafruit-Blinka-Raspberry-Pi5-Neopixel==1.0.0rc2'
"$venv_dir/bin/python" "$HERE/neopixel.py" --check
printf '\nReady. Turn on: python3 %q\nTurn off: python3 %q --off\n' "$HERE/neopixel.py" "$HERE/neopixel.py"
