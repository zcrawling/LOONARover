"""Check launcher arguments without starting hardware services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'start-ground-support.sh'
DEFAULT_DEVICE = '/dev/serial/by-id/usb-Teensyduino_USB_Serial_20356570-if00'


class GroundSupportLauncherTests(unittest.TestCase):
    def launch(self, arguments, payload_device=None):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / 'python3'
            python.write_text('''#!/usr/bin/python3
import argparse, json
p = argparse.ArgumentParser()
p.add_argument('--payload-device')
p.add_argument('--video-ip')
args, _ = p.parse_known_args()
print(json.dumps(vars(args)))
''')
            python.chmod(0o755)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
                       SSH_CONNECTION='10.254.254.2 12345 10.254.254.3 22')
            env.pop('PAYLOAD_DEVICE', None)
            if payload_device is not None:
                env['PAYLOAD_DEVICE'] = payload_device
            result = subprocess.run(['bash', str(SCRIPT), *arguments], env=env,
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

    def test_video_also_starts_payload(self):
        self.assertEqual(self.launch(['--video']),
                         {'payload_device': DEFAULT_DEVICE, 'video_ip': '10.254.254.2'})

    def test_explicit_device_overrides_environment(self):
        result = self.launch(['--video', '--payload-device', '/dev/custom'], '/dev/env')
        self.assertEqual(result['payload_device'], '/dev/custom')

    def test_environment_device_without_video(self):
        self.assertEqual(self.launch([], '/dev/env')['payload_device'], '/dev/env')
