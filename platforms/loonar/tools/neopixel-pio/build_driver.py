#!/usr/bin/env python3
"""Build pinned Raspberry Pi GPL drivers for LOONAR's Ubuntu 6.8 raspi kernel.

Only compatibility changes: 6.8 remove_new callback, deferred firmware discovery,
and an explicit PIO id for runtime overlays (boot-time aliases aren't rescanned).
Upstream license notices remain in every downloaded source/header.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import urllib.request

COMMIT = '5d39807272da852e10f3fc4467c33b57f59ecc61'
SOURCES = {
    'drivers/mailbox/rp1-mailbox.c': '70e3a1e04aa7ed5feea198969fe3650c6e3509cff2ba4a0852112d66030ce96d',
    'drivers/firmware/rp1-fw.c': '19a064d5a5bd6b2bd3826da7d3331c83869b55baf9eed890b3e8c28d40b2c61b',
    'drivers/misc/rp1-pio.c': 'f8ad7a82545597750bd4292c53fe76fef8eb05930c3bb850bb26043481b35bc8',
    'drivers/misc/rp1-fw-pio.h': '8b5ebc93c7a7f4cb222570bee167e1515a0b7622f3545c329159c80830a47d68',
    'include/linux/rp1-firmware.h': 'aec935796eb427441c79e9c794ec25bcfc95dc2dbf2e52bfde55735484a5b89e',
    'include/linux/pio_rp1.h': '1cdf7f09e53955da3819c24d9bf3506382bee295a5ef67721870a6772f99e8b3',
    'include/linux/pio_instructions.h': '61dfc433f5f16df24c1baab781a7274010451a32bd9ceebcbe09fff931d905a3',
    'include/uapi/misc/rp1_pio_if.h': 'c0a881e2b65746d849898e484960772abff0f5abb2778c28e1cfe0a60c3375e6',
}


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('Pinned driver compatibility marker not found exactly once')
    return source.replace(old, new, 1)


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    for path, digest in SOURCES.items():
        original = output/'upstream'/path
        original.parent.mkdir(parents=True, exist_ok=True)
        data = original.read_bytes() if original.exists() else urllib.request.urlopen(
            f'https://raw.githubusercontent.com/raspberrypi/linux/{COMMIT}/{path}', timeout=30).read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f'SHA256 mismatch: {path}')
        original.write_bytes(data)
        destination = output/path if path.startswith('include/') else output/Path(path).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    path = output/'rp1-fw.c'
    source = replace_once(path.read_text(), '.remove\t\t= rp1_firmware_remove,',
                          '.remove_new\t= rp1_firmware_remove,')
    source = replace_once(source, 'if (!pdev)\n\t\treturn ERR_PTR(-ENXIO);',
                          'if (!pdev)\n\t\treturn ERR_PTR(-EPROBE_DEFER);')
    path.write_text(source)
    path = output/'rp1-pio.c'
    source = replace_once(path.read_text(),
        'if (pdev->id < 0)\n\t\treturn dev_err_probe(dev, pdev->id, "alias is missing\\n");',
        'if (pdev->id < 0) {\n\t\tu32 id;\n'
        '\t\tif (of_property_read_u32(dev->of_node, "loonar,pio-id", &id) || id != 0)\n'
        '\t\t\treturn dev_err_probe(dev, -EINVAL, "PIO alias/id is missing\\n");\n'
        '\t\tpdev->id = id;\n\t}')
    path.write_text(source)
    (output/'Makefile').write_text(
        'obj-m += rp1-mailbox.o rp1-fw.o rp1-pio.o\n'
        'ccflags-y += -I$(src)/include -DCONFIG_FIRMWARE_RP1=1 -DCONFIG_RP1_PIO=1\n')
    (output/'source-manifest.json').write_text(json.dumps(dict(
        upstream=f'https://github.com/raspberrypi/linux/tree/{COMMIT}',
        kernel=platform.release(), sha256=SOURCES,
        compatibility_changes=['6.8 remove_new callback', 'defer firmware discovery',
                               'runtime overlay pio-id fallback']), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    prepare(a.output.resolve())
    if not a.prepare_only:
        release = platform.release()
        if not release.startswith('6.8.') or not release.endswith('-raspi'):
            p.error('This compatibility build targets Ubuntu 6.8.x-raspi only')
        subprocess.run(['make', '-C', f'/lib/modules/{release}/build',
                        'M='+str(a.output.resolve()), '-j2', 'modules'], check=True)


if __name__ == '__main__':
    main()
