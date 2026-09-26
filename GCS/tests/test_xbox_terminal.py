"""Exercise the terminal loop with a PTY and synthetic evdev packets, no rover."""
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest

from cli.xbox_control import EVENT, EV_ABS, EV_SYN, SYN_REPORT, LY, RT

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import json, os, sys
from cli import xbox_control as x
read_fd, record = int(sys.argv[1]), sys.argv[2]
def init(self, path):
    self.path = 'synthetic-Xbox'
    self.fd = read_fd
    self.buffer = b''
    self.info = {a: (0, 0 if a in (x.LT, x.RT) else -32768,
                    1023 if a in (x.LT, x.RT) else 32767, 0, 0, 0) for a in x.AXES}
    self.values = {a: 0 for a in x.AXES}
def request(body, timeout=7):
    if body['action'] == 'state':
        return {'source': 'REAL ROVER / synthetic', 'connection': 'CONNECTED', 'status': {'mode': 'STOP'}}
    with open(record, 'a') as f:
        f.write(json.dumps(body) + '\n')
    return {'ok': True, 'text': 'test sent'}
x.XboxDevice.__init__ = init
x.request = request
x.LOCAL_SOCKET = __import__('pathlib').Path(record).parent / 'backend.sock'
sys.argv = ['test', '--device', 'synthetic']
x.main()
'''


class TerminalTests(unittest.TestCase):
    def test_focus_stop_rearm_and_unplug(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / 'commands.jsonl'
            master, slave = pty.openpty()
            read_fd, write_fd = os.pipe()
            process = subprocess.Popen([sys.executable, '-B', '-c', CHILD, str(read_fd), str(record)],
                                       cwd=ROOT, pass_fds=(read_fd,), stdin=slave, stdout=slave, stderr=slave)
            os.close(slave)
            os.close(read_fd)
            output = bytearray()
            def commands():
                return [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
            def wait_for(predicate):
                deadline = time.monotonic() + 5
                while not predicate():
                    self.assertLess(time.monotonic(), deadline, output.decode(errors='replace'))
                    if select.select([master], [], [], .02)[0]:
                        try:
                            output.extend(os.read(master, 65536))
                        except OSError:
                            pass
            def report(axis, value):
                os.write(write_fd, EVENT.pack(0, 0, EV_ABS, axis, value) +
                         EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
            try:
                wait_for(lambda: b'\x1b[?1004h' in output)
                report(RT, 1023)  # An unfocused trigger cannot arm.
                time.sleep(.1)
                self.assertEqual(commands(), [])
                os.write(master, b'\x1b[I')
                report(RT, 0)
                report(RT, 1023)
                report(LY, -32768)
                wait_for(lambda: any(c.get('linear_mps') == 1 for c in commands()))
                os.write(master, b'\x1b[O')
                wait_for(lambda: commands()[-1]['command'] == 'STOP')
                count = len(commands())
                report(LY, 32767)
                os.write(master, b'\x1b[I')
                time.sleep(.2)
                self.assertEqual(len(commands()), count, 'focus return must not resume motion')
                report(RT, 0)
                report(RT, 1023)
                wait_for(lambda: any(c.get('linear_mps') == -1 for c in commands()[count:]))
                os.close(write_fd)
                write_fd = None
                wait_for(lambda: process.poll() is not None)
                self.assertEqual(commands()[-1]['command'], 'STOP')
                self.assertEqual(process.returncode, 1)  # device disconnect is reported
                wait_for(lambda: b'\x1b[?1049l' in output)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
                os.close(master)
                if write_fd is not None:
                    os.close(write_fd)


if __name__ == '__main__':
    unittest.main()
