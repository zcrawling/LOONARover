import csv
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from loonar_apriltag.trial_analysis import analyze, motion_intervals


class IntervalTests(unittest.TestCase):
    def test_pause_clock_offset_and_known_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'rover').mkdir();(p/'camera').mkdir()
            (p/'test.json').write_text(json.dumps({'clock_before':{'best':{'offset_s':100.,'rtt_s':.01}}}))
            events=[]
            for t in np.arange(0,25.01,.05):
                moving=t<10 or 12<=t<25
                events.append(dict(ros_stamp_ns=round((t+100)*1e9),linear_mps=.05 if moving else 0,event='motion' if moving else 'stop' if t>=25 else 'tracking_pause'))
            (p/'rover/command-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            with (p/'rover/wheel-samples.csv').open('w') as f:
                f.write('t,vx,wz\n')
                for t in np.arange(0,25.02,.02):f.write(f'{t+100},0.05,0\n')
            with (p/'camera/frames.csv').open('w') as f:
                wr=csv.writer(f);wr.writerow(['t','valid','s_m','reprojection_px'])
                for t in np.arange(0,25.01,.1):wr.writerow([t,1,t*.04,.3])
            result=analyze(p)
            self.assertGreater(result['accepted'],0)
            with (p/'c_windows.csv').open() as f:rows=list(csv.DictReader(f))
            for row in rows:
                self.assertAlmostEqual(float(row['C']),.8,places=8)
                a,b=float(row['start_ros']),float(row['end_ros'])
                self.assertTrue(102<=a<b<=109.8 or 114<=a<b<=124.8)

    def test_unfinished_segment_not_used(self):
        self.assertEqual(motion_intervals([dict(event='motion',linear_mps=.05,ros_stamp_ns=0)],2),[])
