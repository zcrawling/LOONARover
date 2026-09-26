"""Exercise existing-GCS startup with fake UI tools; no sockets or rover changes."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class WindowsTests(unittest.TestCase):
    def test_existing_gcs_opens_browser_diagnostics_then_video(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            folder = Path(directory)
            runtime = folder / 'runtime'
            runtime.mkdir()
            record = folder / 'calls'
            common = folder / 'common.sh'
            common.write_text(f'GCS_ROOT="{ROOT}"\nRUNTIME_DIR="{runtime}"\nprompt_text() {{ echo 192.168.1.50; }}\nvalid_host() {{ return 0; }}\nshow_error() {{ echo "$1" >&2; }}\n')
            for name, body in {
                'python3': 'echo "REAL ROVER / 192.168.1.50"',
                'xdg-open': 'echo browser >> "$TEST_RECORD"',
                'gnome-terminal': 'echo "$*" >> "$TEST_RECORD"',
            }.items():
                tool = folder / name
                tool.write_text('#!/bin/bash\n' + body + '\n')
                tool.chmod(0o755)
            script = folder / 'start.sh'
            script.write_text((ROOT / 'scripts/start_gcs.sh').read_text())
            env = dict(os.environ, PATH=str(folder)+':'+os.environ['PATH'], TEST_RECORD=str(record))
            result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = record.read_text().splitlines()
            self.assertEqual(calls[0], 'browser')
            self.assertIn('start_diagnostics.sh --host 192.168.1.50', calls[1])
            self.assertIn('start_video.sh', calls[2])
            self.assertIn('--record', calls[2])
            self.assertIn('--compass', calls[2])
            self.assertIn('start_controller.sh', calls[3])

if __name__ == '__main__':
    unittest.main()
