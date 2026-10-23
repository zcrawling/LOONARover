"""Check launcher arguments without starting hardware services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'start-ground-support.sh'
DEFAULT_DEVICE = '/dev/serial/by-id/usb-Teensyduino_USB_Serial_21147480-if00'


class GroundSupportLauncherTests(unittest.TestCase):
    def launch(self, arguments, payload_device=None, legacy=False):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / 'python3'
            python.write_text('''#!/usr/bin/python3
import argparse, json, os
p = argparse.ArgumentParser()
p.add_argument('--payload-device')
p.add_argument('--video-ip')
args, _ = p.parse_known_args()
result = vars(args)
if os.environ.get('LOONAR_FLY_GCS') == '1':
    result.update(route='auto', launcher=os.environ.get('LOONAR_ROS_SAMPLE_LAUNCHER'),
                  capture=os.environ.get('LOONAR_CAPTURE_SESSION'), gcs_ip=os.environ.get('GROUND_STATION_IP'),
                  fly_ip=os.environ.get('LOONAR_FLY_VIDEO_IP'))
if '--record' in _: result['record'] = True
if '--record-all' in _: result['record_all'] = True
print(json.dumps(result))
''')
            python.chmod(0o755)
            bash = Path(directory) / 'bash'
            bash.write_text('''#!/usr/bin/python3
import json, os, sys
print(json.dumps(dict(route='gcs', args=sys.argv[1:],
                     payload_device=os.environ.get('PAYLOAD_DEVICE'))))
''')
            bash.chmod(0o755)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
                       GROUND_STATION_IP='192.0.2.21', LOONAR_NETWORK_CONFIGURED='1')
            env.pop('PAYLOAD_DEVICE', None)
            env.pop('LOONAR_FLY_LEGACY_SUPPORT', None)
            env.pop('LOONAR_FLY_GCS', None)
            env['LOONAR_CAPTURE_SESSION'] = '/tmp/inherited-recording'
            if legacy:
                env['LOONAR_FLY_LEGACY_SUPPORT'] = '1'
            if payload_device is not None:
                env['PAYLOAD_DEVICE'] = payload_device
            result = subprocess.run(['/bin/bash', str(SCRIPT), *arguments], env=env,
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

    def test_video_and_no_arguments_start_same_auto_stack(self):
        default = self.launch([])
        self.assertEqual(self.launch(['--video']), default)
        self.assertEqual(default['route'], 'auto')
        self.assertTrue(default['launcher'].endswith('/fly_brain/start_ros.sh'))
        self.assertIsNone(default['capture'])
        self.assertNotIn('record', default)
        self.assertNotIn('record_all', default)
        self.assertIsNone(default['video_ip'])  # AUTO launcher owns the camera.
        self.assertEqual(default['payload_device'], DEFAULT_DEVICE)

    def test_legacy_override_preserves_video_and_payload(self):
        self.assertEqual(self.launch(['--video'], legacy=True),
                         {'payload_device': DEFAULT_DEVICE, 'video_ip': '192.0.2.21'})

    def test_explicit_device_overrides_environment(self):
        result = self.launch(['--video', '--payload-device', '/dev/custom'], '/dev/env')
        self.assertEqual(result['payload_device'], '/dev/custom')

    def test_environment_device_without_video(self):
        self.assertEqual(self.launch([], '/dev/env')['payload_device'], '/dev/env')

    def test_encoder_verification_keeps_bench_path(self):
        self.assertEqual(self.launch(['--video', '--encoder-verify']),
                         {'payload_device': DEFAULT_DEVICE, 'video_ip': '192.0.2.21'})

    def test_selected_ip_reaches_auto_camera_without_changing_launch_mode(self):
        result = self.launch(['--gcs-ip', '192.0.2.77', '--video'])
        self.assertEqual(result['gcs_ip'], '192.0.2.77')
        self.assertEqual(result['fly_ip'], '192.0.2.77')
        self.assertEqual(result['route'], 'auto')
        self.assertIsNone(result['video_ip'])

    def test_selected_ip_reaches_legacy_sender(self):
        result = self.launch(['--gcs-ip', '192.0.2.78', '--video', '--record'])
        self.assertEqual(result['video_ip'], '192.0.2.78')
        self.assertTrue(result['record'])

    def test_record_options_remain_distinct(self):
        for option in ('--record', '--record-all'):
            result = self.launch(['--video', option])
            self.assertEqual(result.get('record', False), option == '--record')
            self.assertEqual(result.get('record_all', False), option == '--record-all')
            self.assertEqual(result['video_ip'], '192.0.2.21')
            self.assertNotIn('route', result)
