import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from loonar_recording.control_journal import close_clients, clients
from loonar_recording.journal import emit, Reader


class AsyncControlJournal(unittest.TestCase):
    def test_single_record_visible_before_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Path(tmp);(session/'raw').mkdir()
            child=subprocess.Popen([sys.executable,'-m','loonar_recording.control_journal',tmp])
            try:
                deadline=time.monotonic()+5
                while not (session/'control-journal.ready').exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                with patch.dict(os.environ,LOONAR_CAPTURE_SESSION=tmp,LOONAR_CAPTURE_ASYNC_CONTROL='1'):
                    emit('gateway','rx',b'first')
                    emit('gateway','rx',b'second')
                    deadline=time.monotonic()+2
                    seen=[]
                    while len(seen)!=2:
                        self.assertLess(time.monotonic(),deadline)
                        paths=list((session/'raw').glob('*.journal'))
                        if paths:
                            reader=Reader(paths[0]);seen=[]
                            while (item:=reader.read()) is not None:seen.append(item[1])
                            reader.close()
                        time.sleep(.01)
                    self.assertEqual(seen,[b'first',b'second'])
                    close_clients()
            finally:
                close_clients()
                if child.poll() is None:child.terminate();child.wait(timeout=5)

    def test_stalled_disk_worker_does_not_block_producer_and_drains_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Path(tmp);(session/'raw').mkdir()
            child=subprocess.Popen([sys.executable,'-m','loonar_recording.control_journal',tmp])
            try:
                deadline=time.monotonic()+5
                while not (session/'control-journal.ready').exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                child.send_signal(signal.SIGSTOP)
                with patch.dict(os.environ,LOONAR_CAPTURE_SESSION=tmp,LOONAR_CAPTURE_ASYNC_CONTROL='1'):
                    started=time.monotonic()
                    for i in range(1000):
                        self.assertTrue(emit('mcu','rx',bytes(range(64)),kind=33,sequence=i))
                    self.assertLess(time.monotonic()-started,.5)
                    self.assertFalse(list((session/'raw').glob('*.journal')))
                    child.send_signal(signal.SIGCONT)
                    close_clients()
                child.send_signal(signal.SIGINT);self.assertEqual(child.wait(timeout=5),0)
                reader=Reader(next((session/'raw').glob('*.journal')))
                rows=[]
                while (item:=reader.read()) is not None: rows.append(item)
                reader.close()
                self.assertEqual(len(rows),1000)
                self.assertEqual([m['seq'] for m,d in rows],list(range(1,1001)))
                self.assertTrue(all(d==bytes(range(64)) for m,d in rows))
                stats=json.loads(next((session/'raw').glob('*.transport.json')).read_text())
                self.assertEqual(stats['received'],stats['attempted'])
                self.assertEqual(stats['dropped'],0);self.assertTrue(stats['closed'])
            finally:
                child.send_signal(signal.SIGCONT)
                close_clients()
                if child.poll() is None: child.terminate();child.wait(timeout=5)

    def test_overflow_is_bounded_and_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No writer: queue fills, live producer never waits for disk/socket.
            with patch.dict(os.environ,LOONAR_CAPTURE_SESSION=tmp,LOONAR_CAPTURE_ASYNC_CONTROL='1'):
                started=time.monotonic()
                results=[emit('gateway','rx',b'a'*64) for _ in range(5000)]
                self.assertLess(time.monotonic()-started,1)
                client=next(iter(clients.values()))
                self.assertGreater(client.dropped,0)
                self.assertLessEqual(client.pending.qsize(),4096)
                self.assertEqual(results.count(False),client.dropped)
                # Test-only abort: no five-second shutdown wait for absent peer.
                client.abort.set();client.sender.join(timeout=1)
                client.closed=True;client.socket.close();clients.clear()


if __name__=='__main__': unittest.main()
