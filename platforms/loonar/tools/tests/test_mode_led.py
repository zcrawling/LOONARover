import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mode_led import pattern, render_frame, run, WHITE, BLUE, YELLOW, GREEN, RED, BLACK


class PolicyTests(unittest.TestCase):
    def status(self, mode, connected=True, **fields):
        return dict(schema=1, mode=mode, gcs_connected=connected, updated_mono=10., **fields)

    def test_idle_boot_disconnect_stale_and_explicit_stop(self):
        self.assertEqual(pattern({}, [], 10., 'boot'), ('IDLE', WHITE, 'steady'))
        self.assertEqual(pattern(self.status(3), [], 10., 'boot')[0], 'IDLE')
        self.assertEqual(pattern(self.status(2, mode_fresh=False), [], 10., 'boot')[0], 'IDLE')
        self.assertEqual(pattern(self.status(3, explicit_stop=True), [], 10., 'boot'), ('STOP', RED, 'steady'))
        for mode in (1,2,3,4,5):
            self.assertEqual(pattern(self.status(mode, False), [], 10., 'boot')[1], WHITE)
            self.assertEqual(pattern(self.status(mode), [], 12., 'boot')[1], WHITE)
        for bad in (None, [], {'schema':1, 'mode':True},
                    dict(self.status(2), updated_mono=float('nan')), self.status(2, explicit_stop='yes')):
            self.assertEqual(pattern(bad, [], 10., 'boot')[1], WHITE)

    def test_modes_and_only_confirmed_live_payload_blinks(self):
        self.assertEqual(pattern(self.status(2), [], 10., 'boot'), ('MANUAL', BLUE, 'steady'))
        self.assertEqual(pattern(self.status(1), [], 10., 'boot'), ('AUTO', YELLOW, 'steady'))
        self.assertEqual(pattern(self.status(4), [], 10., 'boot')[0], 'IDLE')
        payload = dict(boot_id='boot', updated_mono=10., online=True, sequence_active=True)
        self.assertEqual(pattern(self.status(4), [payload], 10., 'boot'), ('PAYLOAD', GREEN, 'blink'))
        self.assertEqual(pattern(self.status(2), [payload], 10., 'boot')[0], 'PAYLOAD')
        self.assertEqual(pattern(self.status(3, explicit_stop=True), [payload], 10., 'boot')[0], 'STOP')
        for fields in (dict(online=False),dict(sequence_active=False),dict(boot_id='old'),dict(updated_mono=1.)):
            self.assertEqual(pattern(self.status(4), [dict(payload, **fields)], 10., 'boot')[0], 'IDLE')
        self.assertEqual(pattern(self.status(5), [payload], 10., 'boot'), ('REACTION', RED, 'chase'))

    def test_blink_and_adjacent_pair_wrap_without_dark_gap(self):
        green = ('PAYLOAD', GREEN, 'blink')
        self.assertEqual(render_frame(green,16,.01), (GREEN,)*16)
        self.assertEqual(render_frame(green,16,.26), (BLACK,)*16)
        self.assertEqual(render_frame(green,16,.51), (GREEN,)*16)
        for count in (12,16):
            for step in range(count*2):
                frame = render_frame(('REACTION',RED,'chase'), count, step*.1+.001)
                self.assertEqual({i for i,c in enumerate(frame) if c==RED}, {step%count,(step+1)%count})
                self.assertEqual(sum(c==RED for c in frame),2)
        reverse = render_frame(('REACTION',RED,'chase'),16,.101,reverse=True)
        self.assertEqual({i for i,c in enumerate(reverse) if c==RED}, {15,14})


class SocketTests(unittest.TestCase):
    def test_real_datagrams_disconnect_and_sender_stall_restore_white(self):
        class Output:
            frames=[]
            stop=threading.Event()
            def write_frame(self, frame):
                if self.stop.is_set():
                    raise KeyboardInterrupt
                self.frames.append(frame)
            def write(self, rgb):
                self.frames.append((rgb,)*16)
        output = Output()
        with tempfile.TemporaryDirectory() as temp:
            payload_path=Path(temp)/'payload.json'
            args=SimpleNamespace(socket=Path(temp)/'status.sock', payload_status=[payload_path], count=16,
                                 brightness=30,blink_hz=2.,chase_step=.1,reverse=False)
            errors=[]
            def worker():
                try:run(args,output)
                except KeyboardInterrupt:pass
                except Exception as exc:errors.append(exc)
            thread=threading.Thread(target=worker,daemon=True);thread.start()
            sender=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
            try:
                end=time.monotonic()+2
                while not args.socket.exists() and time.monotonic()<end:time.sleep(.01)
                def send(mode, connected=True):
                    sender.sendto(json.dumps(dict(schema=1,mode=mode,gcs_connected=connected,
                        updated_mono=time.monotonic())).encode(), str(args.socket))
                def wait_for(rgb):
                    end=time.monotonic()+2
                    while time.monotonic()<end:
                        if output.frames and output.frames[-1]==(rgb,)*16:return
                        time.sleep(.01)
                    self.fail(f'Expected {rgb}, got {output.frames[-3:]}')
                wait_for(WHITE)
                send(2);wait_for(BLUE)
                send(1);wait_for(YELLOW)
                send(1,False);wait_for(WHITE)
                payload_path.write_text(json.dumps(dict(
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    updated_mono=time.monotonic(),online=True,sequence_active=True)))
                send(4);wait_for(GREEN);wait_for(BLACK)
                payload_path.write_text(json.dumps(dict(
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    updated_mono=time.monotonic(),online=True,sequence_active=False)))
                send(4);wait_for(WHITE)
                send(2);wait_for(BLUE)
                time.sleep(1.1);wait_for(WHITE)
            finally:
                output.stop.set()
                sender.sendto(json.dumps(dict(schema=1,mode=2,gcs_connected=True,
                    updated_mono=time.monotonic())).encode(),str(args.socket))
                thread.join(2);sender.close()
            self.assertFalse(thread.is_alive())
            self.assertEqual(output.frames[-1],(WHITE,)*16)
            self.assertFalse(errors,errors)


if __name__=='__main__':unittest.main()
