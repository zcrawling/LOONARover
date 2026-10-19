"""Fault injection without a CubeEye device; real UDP decoding in the smoke test."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location('tof_send', Path(__file__).with_name('send.py'))
send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(send)


def helper_at(root, body):
    helper = root/'helper'
    helper.write_text('#!/usr/bin/python3\nimport os,struct,sys,time\nfrom pathlib import Path\n'
                      'fd=int(sys.argv[1])\n'+body)
    helper.chmod(0o755)
    return helper


class CaptureTests(unittest.TestCase):
    def test_mount_rotation_maps_raw_right_to_display_up(self):
        raw = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
        np.testing.assert_array_equal(send.rotate_depth(raw, 'left'), [[3, 6], [2, 5], [1, 4]])
        np.testing.assert_array_equal(send.rotate_depth(raw, 'none'), raw)

    def test_exit_and_partial_frame_timeout_recover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = helper_at(root, '''
p=Path(__file__).with_name('attempt')
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
if n==1: sys.exit(1)
packet=struct.pack('<III4H',0x43554245,2,2,n,n,n,n)
os.write(fd,packet)
if n==2:
 os.write(fd,b'CU')
 time.sleep(30)
while True:
 os.write(fd,packet)
 time.sleep(.05)
''')
            stop = threading.Event()
            capture = send.Capture(helper, dict(os.environ), stop, .5, .1)
            capture.thread.start()
            try:
                deadline = time.monotonic()+8
                while time.monotonic() < deadline:
                    frame, count, _ = capture.snapshot()
                    if frame is not None and frame[0, 0] == 3 and count >= 5:
                        break
                    time.sleep(.02)
                else:
                    self.fail('capture did not recover after exit and truncated frame')
                self.assertEqual((root/'attempt').read_text(), '3')
            finally:
                stop.set(); capture.thread.join(5)
            self.assertFalse(capture.thread.is_alive())

    def test_short_frame_gap_does_not_restart_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = helper_at(Path(directory), '''
packet=struct.pack('<IIIH',0x43554245,1,1,123)
os.write(fd,packet)
time.sleep(.3)
os.write(fd,packet)
time.sleep(30)
''')
            stop = threading.Event()
            capture = send.Capture(helper, dict(os.environ), stop, 1, .1)
            capture.thread.start()
            try:
                deadline = time.monotonic()+3
                while capture.snapshot()[1] < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(capture.snapshot()[1], 2)
                self.assertEqual(int(capture.snapshot()[0][0, 0]), 123)
            finally:
                stop.set(); capture.thread.join(5)
            self.assertFalse(capture.thread.is_alive())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
    def test_udp_video_survives_camera_restart_and_sigint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = helper_at(root, '''
p=Path(__file__).with_name('attempt')
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
packet=struct.pack('<III',0x43554245,640,480)+struct.pack('<H',500+n)*640*480
for i in range(100):
 data=packet
 while data: data=data[os.write(fd,data):]
 if n==1 and i==3: sys.exit(1)
 time.sleep(.05)
''')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            receiver = subprocess.Popen([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-probesize', '32768',
                '-analyzeduration', '100000', '-i', f'udp://127.0.0.1:{port}',
                '-frames:v', '25', '-f', 'framemd5', 'pipe:1'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log = (root/'monitor.log').open('w+')
            monitor = subprocess.Popen([
                '/usr/bin/python3', str(Path(send.__file__)), '127.0.0.1', '--port', str(port),
                '--helper', str(helper), '--retry-delay', '.3'],
                env=dict(os.environ, XDG_RUNTIME_DIR=str(root)), stdout=log, stderr=log)
            try:
                out, errors = receiver.communicate(timeout=15)
                self.assertEqual(receiver.returncode, 0, errors.decode())
                frames = [line for line in out.splitlines() if line and not line.startswith(b'#')]
                self.assertEqual(len(frames), 25)
                self.assertIn(b'480x640', out)
                self.assertGreaterEqual(int((root/'attempt').read_text()), 2)
                self.assertIsNone(monitor.poll())
                monitor.send_signal(signal.SIGINT)
                self.assertEqual(monitor.wait(timeout=6), 0)
            finally:
                for process in (monitor, receiver):
                    if process.poll() is None: process.kill()
                    process.wait()
                receiver.stdout.close(); receiver.stderr.close(); log.close()


if __name__ == '__main__':
    unittest.main()
