import csv
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from loonar_imu_vibration.core import Config, Engine, Predictor, SCHEMA, features, integrate_wheel
from loonar_imu_vibration.data import ground_truth, write_json
from loonar_imu_vibration.pipeline import evaluate_run, fit, make_dataset


def series(end=3, reverse=False):
    records=[]
    for i in range(round(end*100)+1):
        t=i/100
        records.append(dict(kind='imu',t=t,ax=0.1*np.sin(2*np.pi*10*t),ay=0.0,az=9.81,
                            gx=0.0,gy=0.0,gz=0.0))
        if i%2==0:
            records.append(dict(kind='wheel',t=t,vx=-0.1 if reverse else 0.1,wz=0.0))
    return records


def create_run(root, name, c=0.5, gt=True, reverse=False):
    path=root/name
    path.mkdir()
    records=series(reverse=reverse)
    write_json(path/'run.json',dict(run_id=name,terrain_id='synthetic',profile_id='test-only',
               preparation_id=name,gt_kind='external',gt_source='synthetic-test-fixture',
               no_slip=False,actual_distance_m=0.15))
    (path/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    if gt:
        with (path/'gt.csv').open('w') as stream:
            writer=csv.writer(stream)
            writer.writerow(['t','s_m'])
            for i in range(151):
                t=i*.02
                writer.writerow([t,(-1 if reverse else 1)*.1*t*c])
    return path


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.cfg=Config()
        self.engine=Engine(self.cfg,Predictor(None,self.cfg,'test-only'))
        for r in series():
            self.engine.add(r['kind'],[r['t']]+([r[k] for k in ('ax','ay','az','gx','gy','gz')] if r['kind']=='imu' else [r['vx'],r['wz']]))

    def test_known_sinusoid_and_gravity(self):
        c,score,reason,f=self.engine.estimate(3)
        self.assertEqual((c,score,reason),(1,0,'no_model'))
        self.assertAlmostEqual(f['az_raw_mean'],9.81)
        self.assertAlmostEqual(f['az_hp_rms'],0)
        self.assertAlmostEqual(f['ax_raw_rms'],.1/np.sqrt(2),delta=.001)
        self.assertEqual(len(f),112)

    def test_no_future_imu(self):
        before=self.engine.estimate(3)[3]
        self.engine.add('imu',[3.01,100,100,100,100,100,100])
        after=self.engine.estimate(3)[3]
        self.assertEqual(before,after)

    def test_gap_and_timestamp_reset(self):
        imu=list(self.engine.imu)
        imu=[v for v in imu if not 2.4<v[0]<2.6]
        self.assertEqual(features(imu,list(self.engine.wheel),3,self.cfg)[1],'imu_gap')
        self.assertFalse(self.engine.add('imu',[1,0,0,0,0,0,0]))
        self.assertIsNone(self.engine.estimate(3)[3])

    def test_denominator_and_reversal(self):
        imu=list(self.engine.imu)
        wheel=[[t,0,w] for t,v,w in self.engine.wheel]
        self.assertEqual(features(imu,wheel,3,self.cfg)[1],'small_encoder_distance')
        wheel=[[t,(-.01 if t<2.2 else .1),w] for t,v,w in self.engine.wheel]
        self.assertEqual(features(imu,wheel,3,self.cfg)[1],'direction_reversal')

    def test_right_endpoint_integral(self):
        self.assertAlmostEqual(integrate_wheel([[0,99,0],[1,.2,0],[2,-.1,0]],.5,1.5),.05)

    def test_prediction_bounds_support_and_profile(self):
        model=dict(schema=SCHEMA,config=asdict(self.cfg),profile_id='a',feature_names=['x'],
                   mean=[0.],scale=[1.],coef=[1.],intercept=.5)
        p=Predictor(model,self.cfg,'a')
        self.assertEqual(p.predict({'x':0})[0],.5)
        self.assertEqual(p.predict({'x':-.5})[0],0)
        self.assertEqual(p.predict({'x':-1})[2],'c_out_of_range')
        self.assertEqual(p.predict({'x':8})[2],'out_of_training_support')
        self.assertEqual(p.predict({'bad':0})[2],'feature_schema_mismatch')
        with self.assertRaises(ValueError):Predictor(model,self.cfg,'different-sensor')


class PipelineTests(unittest.TestCase):
    def test_endpoint_measurement_does_not_become_window_gt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=create_run(Path(tmp),'no_gt',gt=False)
            d=make_dataset([run],Config())
            self.assertGreater(len(d['samples']),10)
            self.assertTrue(all(s['c_v'] is None for s in d['samples']))

    def test_external_gt_reverse_stuck_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,c,reverse in [('reverse',.7,True),('blocked',0,False)]:
                d=make_dataset([create_run(root,name,c=c,reverse=reverse)],Config())
                self.assertTrue(all(abs(s['c_v']-c)<1e-6 for s in d['samples']))
            run=create_run(root,'gap')
            (run/'gt.csv').write_text('t,s_m\n0,0\n1,.05\n3,.15\n')
            gt=ground_truth(run,json.loads((run/'run.json').read_text()),.2)
            self.assertIsNone(gt(1,3))

    def test_split_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=[create_run(root,n) for n in ['a','b','c']]
            d=make_dataset(paths,Config())
            with self.assertRaises(ValueError):fit(d,dict(train=['a'],validation=['a'],test=['c']))
            for m in d['runs'].values():m['preparation_id']='same'
            with self.assertRaises(ValueError):fit(d,dict(train=['a'],validation=['b'],test=['c']),True)

    def test_end_to_end_causal_evaluation_not_window_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=[create_run(root,n) for n in ['a','b','c']]
            d=make_dataset(paths,Config())
            model=fit(d,dict(train=['a'],validation=['b'],test=['c']),True)
            report=evaluate_run(paths[-1],model,Config())
            self.assertAlmostEqual(report['baseline_distance_m'],.3)
            self.assertAlmostEqual(report['gt_distance_m'],.15)
            # First ~1 s correctly remains uncorrected while history fills.
            self.assertGreater(report['corrected_distance_m'],.19)
            self.assertLess(report['corrected_distance_m'],.21)
            self.assertLess(abs(report['corrected_final_error_m']),abs(report['baseline_final_error_m']))
            self.assertFalse(model['approved_for_use'])


if __name__=='__main__':unittest.main()
