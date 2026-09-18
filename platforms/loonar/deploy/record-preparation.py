#!/usr/bin/env python3
"""Read installed-file metadata; never start a service or open a sensor."""
import datetime
import hashlib
import json
import platform
import subprocess
from pathlib import Path


def read_command(*args):
    result = subprocess.run(args, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main():
    root = Path(__file__).resolve().parents[3]
    output = Path.home() / 'loonar-staging/preparation-manifest.json'
    units = ['vehicle_gatewayd.service', 'loonar-cfs.service', 'loonar-core.target',
             'loonar-localization.service', 'loonar-video.service', 'loonar-tof.service']
    binaries = [Path('/opt/loonar/current/bin/vehicle_gatewayd'),
                Path('/opt/loonar/current/bin/vehicle_gatewayctl'),
                Path('/opt/loonar/current/bin/capture_xyz'),
                Path('/opt/loonar/current/cfs/core-cpu1'),
                Path('/opt/loonar/camera-stack/current/bin/rpicam-hello'),
                Path.home() / 'loonar-staging/firmware/control-usb/firmware.hex',
                Path.home() / 'loonar-staging/firmware/control-uart/firmware.hex']
    packages = [line for line in (root/'platforms/loonar/deploy/apt-packages.txt').read_text().splitlines()
                if line and not line.startswith('#')]
    sources = {'loonar': root, 'cfs': root/'build/gcs-test/cFS',
               'libcamera': root/'build/pi-camera/libcamera',
               'libpisp': root/'build/pi-camera/libcamera/subprojects/libpisp',
               'rpicam-apps': root/'build/pi-camera/rpicam-apps'}
    report = {
        'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'hostname': platform.node(), 'architecture': platform.machine(),
        'kernel': platform.release(), 'os_release': Path('/etc/os-release').read_text(),
        'release': str(Path('/opt/loonar/current').resolve(strict=True)),
        'source_revisions': {name: read_command('git', '-C', str(path), 'rev-parse', 'HEAD')
                             for name, path in sources.items()},
        'source_status': read_command('git', '-C', str(root), 'status', '--short'),
        'packages': read_command('dpkg-query', '-W', '-f=${binary:Package} ${Version} ${db:Status-Status}\n', *packages),
        'artifact_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries},
        'services': {u: read_command('systemctl', 'show', u, '-p', 'LoadState', '-p', 'ActiveState',
                                     '-p', 'SubState', '-p', 'UnitFileState') for u in units},
        'runtime_tests': 'NOT RUN: preparation only, per user instruction',
        'sensor_capture': 'NOT RUN', 'firmware_upload': 'NOT RUN',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(output)


if __name__ == '__main__':
    main()
