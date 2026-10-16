import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import cv2 as cv
import numpy as np

from loonar_apriltag.manual_session import arguments, main, remote_command
from loonar_apriltag.session_time import align_session, clock_mapping
from loonar_apriltag.tracking import LatestCapture
from loonar_apriltag.video_archive import VideoArchive

TOOLS = Path(__file__).resolve().parents[1]


class TimingTests(unittest.TestCase):
    def test_interpolation_endpoint_and_delay_sign_preserve_sources(self):
        samples = [dict(local_epoch=100., offset_s=2., rtt_s=.01),
                   dict(local_epoch=110., offset_s=2.02, rtt_s=.02)]
        self.assertAlmostEqual(clock_mapping(samples, 105.)[0], 2.01)
        self.assertEqual(clock_mapping(samples, 90.), (2., .005))
        self.assertEqual(clock_mapping(samples, 120.), (2.02, .01))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'camera').mkdir()
            (root/'session.json').write_text(json.dumps(dict(camera_delay_s=.08)))
            (root/'clock_samples.jsonl').write_text('\n'.join(json.dumps(dict(best=s)) for s in samples))
            source = 'frame,read_started_epoch,read_completed_epoch,receipt_monotonic_ns\n0,104.99,105.0,1000000000\n1,105.99,106.0,2000000000\n'
            (root/'camera/video_frames.csv').write_text(source)
            (root/'controller.jsonl').write_text(json.dumps(dict(laptop_epoch_ns=105000000000, event='issued'))+'\n')
            summary = align_session(root)
            with (root/'timestamps.csv').open() as file:
                rows = list(csv.DictReader(file))
            self.assertAlmostEqual(float(rows[0]['pi_epoch']), 105.+2.01-.08)
            command = json.loads((root/'controller_pi.jsonl').read_text())
            self.assertAlmostEqual(command['pi_epoch'], 107.01)  # camera delay never applied to controls
            self.assertEqual((root/'camera/video_frames.csv').read_text(), source)
            self.assertEqual(summary['laptop_clock_steps'], 0)
            self.assertEqual(summary['frames'], 2)
            (root/'camera/video_frames.csv').write_text(source.replace('105.99,106.0', '104.49,104.5'))
            self.assertTrue(align_session(root)['timing_review_required'])

    def test_dry_run_has_no_external_side_effects(self):
        with patch('loonar_apriltag.manual_session.subprocess.Popen') as popen, \
             patch('loonar_apriltag.manual_session.subprocess.run') as run:
            self.assertEqual(main(['--dry-run']), 0)
            popen.assert_not_called()
            run.assert_not_called()
        for option in ('--duration', '--camera-delay-s', '--fps'):
            with self.assertRaises(SystemExit):
                arguments([option, 'nan'])


class ArchiveTests(unittest.TestCase):
    def test_slow_tracking_does_not_remove_raw_video_frames(self):
        produced, release = threading.Event(), threading.Event()
        class Camera:
            count = 0
            def read(self):
                self.count += 1
                if self.count == 7:
                    produced.set()
                    release.wait(5)
                return True, np.full((48,64,3), self.count*20, np.uint8)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = VideoArchive(root, 64, 48, 30)
            capture = LatestCapture(Camera(), on_frame=archive)
            try:
                self.assertTrue(produced.wait(3))
                frame, _, _, skipped = capture.read()
                self.assertEqual(skipped, 5)
                self.assertEqual(capture.consumed-1, 5)
                self.assertEqual(int(frame[0,0,0]), 120)
            finally:
                capture.stopped = True
                release.set()
                capture.close()
                archive.close()
            with (root/'video_frames.csv').open() as file:
                rows = list(csv.DictReader(file))
            video = cv.VideoCapture(str(root/'video.avi'))
            try:
                count = 0
                while video.read()[0]:
                    count += 1
            finally:
                video.release()
            self.assertGreaterEqual(count, 6)
            self.assertEqual(count, len(rows))
            self.assertEqual([int(row['frame']) for row in rows], list(range(count)))


class RemoteSupervisorTests(unittest.TestCase):
    def run_remote(self, fail=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tools = root/'platforms/loonar/tools'
            tools.mkdir(parents=True)
            record = '''import pathlib,signal,sys,time
out=pathlib.Path(sys.argv[1]);out.mkdir()
(out/'data.mcap').write_bytes(b'fake mcap payload')
def stop(*_):
 (out/'metadata.yaml').write_text('rosbag2_bagfile_information: {}')
 sys.exit(0)
signal.signal(signal.SIGINT,stop)
while True:time.sleep(.05)
'''
            if fail:
                record = 'import sys;sys.exit(7)'
            (tools/'fake_record.py').write_text(record)
            (tools/'record-drive.sh').write_text('exec '+sys.executable+' '+str(tools/'fake_record.py')+' "$1" "ros2 bag record"\n')
            monitor = '''import json,pathlib,signal,sys,time
p=pathlib.Path(sys.argv[1])
signal.signal(signal.SIGINT,lambda *_:sys.exit(0))
while True:
 t=p.with_suffix('.tmp');t.write_text(json.dumps(dict(stamp_ns=time.time_ns(),streams_fresh=True,missing_or_stale=[])));t.replace(p)
 time.sleep(.1)
'''
            (tools/'fake_monitor.py').write_text(monitor)
            (tools/'run-recording-monitor.sh').write_text('exec '+sys.executable+' '+str(tools/'fake_monitor.py')+' "$1"\n')
            if getattr(self, 'owned_stack', False):
                support = root/'support.py'
                support.write_text("""import argparse,json,pathlib,signal,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--record-all',action='store_true');p.add_argument('--runtime',type=pathlib.Path);p.add_argument('--bag-dir',type=pathlib.Path);a=p.parse_args()
assert a.record_all
a.runtime.mkdir(parents=True);a.bag_dir.mkdir(parents=True)
(a.runtime/'args.json').write_text(json.dumps(sys.argv[1:]))
tools=pathlib.Path(__file__).parent/'platforms/loonar/tools'
record=subprocess.Popen([sys.executable,str(tools/'fake_record.py'),str(a.bag_dir/'drive_fixture'),'ros2 bag record'])
monitor=subprocess.Popen([sys.executable,str(tools/'fake_monitor.py'),str(a.runtime/'recording-status.json')])
stopped=False
def stop(*_):
 global stopped
 stopped=True
signal.signal(signal.SIGINT,stop)
while not stopped:time.sleep(.05)
for child in (monitor,record):
 child.send_signal(signal.SIGINT);child.wait(timeout=3)
""")
                (tools/'start-ground-support.sh').write_text('exec '+sys.executable+' '+str(support)+' "$@"\n')
            # Exercise the laptop orchestrator with real subprocesses, replacing only
            # the camera device and SSH transport. The encoded remote supervisor runs.
            if getattr(self, 'whole_session', False):
                ssh_tool = root/'ssh.py'
                ssh_tool.write_text("import os,sys\ncommand=sys.argv[-1]\nif command.startswith('python3 '):os.execlp('bash','bash','-c',command)\n")
                camera_tool = root/'camera.py'
                camera_tool.write_text("import pathlib,signal,sys,time\np=pathlib.Path(sys.argv[1]);p.mkdir()\n(p/'video_frames.csv').write_text('frame,read_started_epoch,read_completed_epoch,receipt_monotonic_ns\\n0,99.99,100.0,1000000000\\n')\nsignal.signal(signal.SIGINT,lambda *_:sys.exit(0))\nwhile True:time.sleep(.05)\n")
                calibration = root/'calibration.json'
                calibration.write_text(json.dumps(dict(width=64,height=48)))
                laptop = root/'laptop'
                popen = subprocess.Popen
                def launch(cmd, **kwargs):
                    if str(TOOLS/'gt.py') in cmd:
                        camera_path = cmd[cmd.index('--output')+1]
                        cmd = [sys.executable, str(camera_tool), camera_path]
                    return popen(cmd, **kwargs)
                sample = dict(best=dict(local_epoch=100.,offset_s=2.,rtt_s=.01),samples=[])
                with patch('loonar_apriltag.manual_session.authenticated', return_value=[sys.executable,str(ssh_tool)]), \
                     patch('loonar_apriltag.manual_session.clock_probe', return_value=sample), \
                     patch('loonar_apriltag.manual_session.subprocess.Popen', side_effect=launch):
                    code = main(([] if getattr(self, 'owned_stack', False) else ['--existing-stack'])+['--no-controller','--no-copy','--duration','.1',
                        '--remote-root',str(root),'--remote-output-root',str(root/'pi'),
                        '--calibration',str(calibration),'--output',str(laptop)])
                state = json.loads((laptop/'session.json').read_text())
                self.assertEqual(code, 0, state)
                self.assertEqual(state['status'], 'complete')
                self.assertEqual(state['remote_exit_code'], 0)
                self.assertEqual(state['timing']['frames'], 1)
                self.assertTrue((laptop/'timestamps.csv').is_file())
                self.assertTrue(list((root/'pi/laptop').rglob('metadata.yaml')))
                if getattr(self, 'owned_stack', False):
                    args = json.loads((root/'pi/laptop/runtime/args.json').read_text())
                    self.assertIn('--record-all', args)
                return
            output = root/'output'
            events = []
            with (root/'events.log').open('w') as file:
                child = subprocess.Popen([sys.executable, str(TOOLS/'loonar_apriltag/remote_manual.py'),
                    '--root', str(root), '--output', str(output), '--existing-stack', '--startup-timeout', '5'],
                    stdin=subprocess.PIPE, stdout=file, stderr=subprocess.STDOUT, text=True)
                try:
                    deadline = time.monotonic()+12
                    while child.poll() is None and time.monotonic()<deadline:
                        child.stdin.write('HEARTBEAT\n'); child.stdin.flush()
                        text = (root/'events.log').read_text()
                        if '"event": "ready"' in text:
                            # EOF must cleanly finalize the recorder even without STOP.
                            child.stdin.close()
                            break
                        time.sleep(.1)
                    child.wait(timeout=10)
                finally:
                    if child.poll() is None:
                        child.kill(); child.wait()
                    if child.stdin and not child.stdin.closed:
                        child.stdin.close()
            events = [json.loads(line) for line in (root/'events.log').read_text().splitlines()]
            state = json.loads((output/'session.json').read_text())
            if fail:
                self.assertEqual(child.returncode, 1)
                self.assertEqual(state['status'], 'failed')
                self.assertNotIn('ready', [e['event'] for e in events])
            else:
                self.assertEqual(child.returncode, 0, events)
                self.assertEqual(state['status'], 'complete')
                self.assertEqual(state['stop_reason'], 'ssh_stdin_eof')
                self.assertTrue((output/'bag/metadata.yaml').is_file())
                self.assertIn('ready', [e['event'] for e in events])

    def test_owned_record_all_stack_records_and_finalizes(self):
        self.whole_session = self.owned_stack = True
        self.run_remote()

    def test_whole_laptop_session_finalizes_remote_bag_and_aligns_video(self):
        self.whole_session = True
        self.run_remote()

    def test_eof_finalizes_owned_bag(self):
        self.run_remote()

    def test_recorder_start_failure_never_reports_ready(self):
        self.run_remote(fail=True)


class ReplayTests(unittest.TestCase):
    def test_offline_retracking_preserves_every_timestamp_and_missing_tags(self):
        spec = importlib.util.spec_from_file_location('retrack_session', TOOLS/'retrack_session.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            camera = root/'camera'; camera.mkdir()
            (root/'session.json').write_text(json.dumps(dict(camera_delay_s=0.)))
            (root/'clock_samples.jsonl').write_text(json.dumps(dict(best=dict(local_epoch=100., offset_s=3., rtt_s=.01)))+'\n')
            (camera/'capture.json').write_text(json.dumps(dict(tag_id=0, tag_size=.15, calibration=dict(
                width=640,height=480,K=[[600,0,320],[0,600,240],[0,0,1]],D=[0]*5))))
            archive = VideoArchive(camera, 640, 480, 30)
            marker = cv.aruco.generateImageMarker(cv.aruco.getPredefinedDictionary(cv.aruco.DICT_APRILTAG_36h11), 0, 150)
            for index in range(3):
                frame = np.full((480,640,3),255,np.uint8)
                if index != 1:
                    frame[150:300,250:400] = cv.cvtColor(marker,cv.COLOR_GRAY2BGR)
                archive(frame,100+index-.01,100+index,index,1000000000+index*1000000000)
            archive.close()
            result = module.retrack(root, root/'tracking', preview=False)
            self.assertTrue(result['complete'])
            self.assertEqual(result['frames'], 3)
            with (root/'tracking/poses.csv').open() as file:
                poses = list(csv.DictReader(file))
            self.assertEqual([float(row['pi_epoch']) for row in poses], [103.,104.,105.])
            self.assertEqual([row['valid'] for row in poses], ['1','0','1'])
            self.assertEqual(poses[1]['reason'], 'tag_missing')
            self.assertTrue(poses[0]['r00'])
