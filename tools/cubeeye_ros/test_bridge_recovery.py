"""Run with the local ROS environment sourced; uses synthetic XYZ, no hardware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RecoveryTest(unittest.TestCase):
    def check_recovery(self, failure):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / 'helper'
            helper.write_text('''#!/usr/bin/python3
import os, struct, sys, time
from pathlib import Path
marker = Path(__file__).with_name('started')
first = not marker.exists()
marker.touch()
fd = int(sys.argv[1])
for i in range(1000):
    stamp = time.time_ns()
    os.write(fd, struct.pack('<IIIQQfff', 0x58595A31, 1, 1, stamp, i, 0., 0., 1.))
    if first:
        if FAILURE == 'eof': sys.exit(0)
        time.sleep(30)
    time.sleep(.04)
'''.replace('FAILURE', repr(failure)))
            helper.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('bridge.py')),
                 '--helper', str(helper), '--sdk', str(root), '--no-base-tf',
                 '--seconds', '3', '--hz', '20', '--stride', '1',
                 '--frame-timeout', '.2', '--startup-timeout', '1', '--retry-delay', '.05'],
                env={**os.environ, 'ROS_DOMAIN_ID': '151'}, capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(x) for x in result.stdout.splitlines() if x.startswith('{')]
            restarts = [x for x in records if x['state'] == 'RESTARTING']
            self.assertEqual(len(restarts), 1, records)
            frames = [x for x in records if 'host_callback_ns' in x]
            self.assertTrue(any(x['restarts'] == 1 and x['frames'] >= 6 for x in frames), records)
            self.assertTrue(all(b['host_callback_ns'] > a['host_callback_ns'] for a, b in zip(frames, frames[1:])))

    def test_stall_after_first_frame(self):
        self.check_recovery('stall')

    def test_helper_eof(self):
        self.check_recovery('eof')


if __name__ == '__main__':
    unittest.main()
