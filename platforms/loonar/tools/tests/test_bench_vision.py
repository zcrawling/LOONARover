"""Exercise bench vision lifecycle with fake children, without ROS or hardware."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcu_v2 import motor_bench


class BenchVisionTests(unittest.TestCase):
    def run_bench(self, enabled):
        real_popen = subprocess.Popen
        launched = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gateway = root/'gateway'
            gateway.touch()
            config = root/'vision.yaml'
            config.touch()

            def fake_child(command, **kwargs):
                env = kwargs['env']
                name = ('vision' if command[-1].endswith('run-vision.sh') else
                        'video' if command[-1].endswith('run-video.sh') else
                        'gateway' if str(gateway) in command else 'backend')
                launched.append((name, dict(env)))
                # A failed detector must not end the bench before the gateway.
                delay = .1 if name == 'vision' else .5 if name == 'gateway' else 30
                return real_popen([sys.executable, '-c', f'import time; time.sleep({delay})'], **kwargs)

            def fake_run(command, **kwargs):
                return subprocess.CompletedProcess(command, 1 if command[0] == 'systemctl' else 0)

            env = {'LOONAR_VISION_CONFIG': str(config), 'LOONAR_VISION_PYTHON': sys.executable,
                   'LOONAR_FLY_VISION': str(int(bool(enabled)))}
            if enabled is None:
                del env["LOONAR_FLY_VISION"]
            args = ['motor_bench', '--registry', str(root/'registry'), '--runtime', str(root/'runtime'),
                    '--gateway-bin', str(gateway), '--video-ip', '10.254.254.2']
            with patch.dict(os.environ, env), patch.object(sys, 'argv', args), \
                 patch.object(motor_bench, 'load', return_value={}), \
                 patch.object(motor_bench, 'geometry', return_value={}), \
                 patch.object(motor_bench.signal, 'signal'), \
                 patch.object(motor_bench.subprocess, 'run', side_effect=fake_run), \
                 patch.object(motor_bench.subprocess, 'Popen', side_effect=fake_child):
                if enabled is None:
                    os.environ.pop("LOONAR_FLY_VISION", None)
                with self.assertRaisesRegex(RuntimeError, 'gateway exited'):
                    motor_bench.main()
            video = next(env for name, env in launched if name == 'video')
            if enabled:
                vision = next(env for name, env in launched if name == 'vision')
                self.assertEqual(video['VISION_ENABLED'], '1')
                self.assertEqual(video['VISION_SOCKET'], vision['VISION_SOCKET'])
                self.assertFalse(Path(video['VISION_SOCKET']).parent.exists())
            else:
                self.assertNotIn('vision', [name for name, _ in launched])
                self.assertEqual(video['VISION_ENABLED'], '0')

    def test_shared_camera_and_detector_failure_isolation(self):
        self.run_bench(True)

    def test_explicit_opt_out(self):
        self.run_bench(False)

    def test_default_uses_gcs_detection(self):
        self.run_bench(None)


if __name__ == '__main__':
    unittest.main()
