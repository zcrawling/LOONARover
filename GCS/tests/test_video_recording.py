"""Local synthetic UDP video only; never connect to a rover or open a window."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg required')
class VideoRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'scripts'
        self.bin.mkdir()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        shutil.copy(SCRIPTS / 'common.sh', self.bin)
        # Isolate the receiver port and lock from the actual GCS.
        (self.bin / 'start_video.sh').write_text(
            (SCRIPTS / 'start_video.sh').read_text().replace('5600', str(self.port)))
        # A decoder consumes the preview pipe in place of a graphical player.
        player = self.bin / 'ffplay'
        player.write_text('#!/bin/bash\nexec ffmpeg -nostdin -hide_banner -loglevel error '
                          '-probesize 32 -analyzeduration 0 -i pipe:0 -t 1 -f null -\n')
        player.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        LOONAR_VIDEO_DIR=str(self.root / 'recordings'), DISPLAY='')

    def start_receiver(self):
        process = subprocess.Popen(['bash', str(self.bin / 'start_video.sh'), '--record',
                                    '--rotate-left'], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, start_new_session=True)
        self.addCleanup(self.stop_group, process)
        return process

    @staticmethod
    def stop_group(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def test_udp_recording_and_preview_close(self):
        receiver = self.start_receiver()
        time.sleep(0.3)
        sender = subprocess.Popen([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-re',
            '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=10',
            '-t', '10', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-tune', 'zerolatency', '-g', '10', '-f', 'mpegts',
            f'udp://127.0.0.1:{self.port}?pkt_size=1316'],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        self.addCleanup(self.stop_group, sender)
        output, _ = receiver.communicate(timeout=12)
        recordings = list((self.root / 'recordings').glob('*.ts'))
        self.assertEqual(len(recordings), 1, output)
        result = subprocess.run(['ffprobe', '-v', 'error', '-count_frames',
                                 '-show_streams', '-of', 'json', str(recordings[0])],
                                capture_output=True, text=True, check=True)
        video = json.loads(result.stdout)['streams'][0]
        self.assertEqual(video['codec_name'], 'h264')
        self.assertEqual((video['width'], video['height']), (160, 120))
        self.assertGreater(int(video['nb_read_frames']), 0)
        self.assertFalse(list((self.root / '.runtime').glob('video-preview.*')))

    def test_interrupt_while_waiting_for_udp_stops_children(self):
        receiver = self.start_receiver()
        time.sleep(0.3)
        receiver.send_signal(signal.SIGINT)
        output, _ = receiver.communicate(timeout=5)
        self.assertEqual(receiver.returncode, 130, output)
        self.assertFalse(list((self.root / '.runtime').glob('video-preview.*')))


if __name__ == '__main__':
    unittest.main()
