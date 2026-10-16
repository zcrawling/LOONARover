#!/usr/bin/env bash
# Recreate PIO support on Ubuntu 6.8 without modifying the boot configuration.
set -euo pipefail
if [[ -c /dev/pio0 ]]; then
    exit 0
fi
resource_dir=/usr/local/lib/loonar-neopixel
if [[ $(uname -r) != "$(cat "$resource_dir/kernel-release")" ]]; then
    echo 'Kernel changed: rerun platforms/loonar/tools/setup-neopixel.sh for this kernel.' >&2
    exit 1
fi
modprobe rp1_mailbox
modprobe rp1_fw
modprobe rp1_pio
if ! dtoverlay -l 2>/dev/null | grep -qE '[[:space:]]loonar-rp1-pio$'; then
    dtoverlay -d "$resource_dir" loonar-rp1-pio
fi
for _ in {1..50}; do
    if [[ -c /dev/pio0 ]]; then
        udevadm settle
        exit 0
    fi
    sleep .1
done
echo 'PIO driver did not create /dev/pio0; inspect journalctl -k for rp1-firmware/rp1-pio.' >&2
exit 1
