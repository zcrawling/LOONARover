import unittest
from types import SimpleNamespace
import numpy as np
from pipeline import integral,delta,robust_line,windows,CORE,terrain_at
from analyze import fit,predict,disjoint

class PipelineTests(unittest.TestCase):
 def test_irregular_integral_and_robust_progress(self):
  t=np.array([0.,.05,.14,.31,.6,1.]);s=integral(t,np.full(len(t),.1));self.assertAlmostEqual(delta(t,s,.2,.8),.06)
  t=np.linspace(0,1,31);p=.08*t+2;p[15]+=.1
  beta,rms=robust_line(t,p);self.assertAlmostEqual(beta[1],.08,places=6)
 def test_actual_local_ratio_and_stuck_retained(self):
  args=SimpleNamespace(window=1.,step=.2,min_tag_samples=6,tag_gap=.25,epsilon=.02,reprojection=1.5,heading_range=3.,gt_rms=.003,c_min=-.2,c_max=2,c_time_range=.04,speed_bins=[0,.075,.15],no_slip_tolerance=.03,slip_threshold=.05)
  t=np.arange(0,3.01,.01);cam=np.arange(0,3.01,.05)
  for factor in [.8,0.]:
   data=dict(im=np.column_stack([t,np.zeros((len(t),6))]),wh=np.column_stack([t,np.full(len(t),.1),np.zeros(len(t))]),rates=np.column_stack([t,np.full((len(t),2),.1)]),gt=np.column_stack([cam,.1*factor*cam,np.zeros((len(cam),4))]),alltimes=cam,command=np.column_stack([t,np.full(len(t),.1),np.zeros(len(t))]),intervals=[(.5,2.5)])
   rows,bad,_=windows(data,'test',args,{},{});self.assertTrue(rows);self.assertFalse(bad)
   for r in rows:self.assertAlmostEqual(r['C_GT'],factor,places=6);self.assertAlmostEqual(r['Delta_s_encoder'],.1,places=6)
 def test_metadata_boundary_and_nonoverlap(self):
  meta={'r':{'intervals':[dict(start_ros=0,end_ros=1,terrain_id='soil'),dict(start_ros=1,end_ros=2,terrain_id='grass')]}}
  self.assertEqual(terrain_at(meta,'r',.2,.8),'soil');self.assertEqual(terrain_at(meta,'r',.5,1.5),'mixed')
  rr=[dict(run_id='r',timestamp_start=i/5,timestamp_end=1+i/5) for i in range(11)]
  self.assertEqual(len(disjoint(rr)),3)
 def test_ridge_has_no_identity_predictor(self):
  train=[dict(run_id=str(i%2),C_GT=1+.2*i,f=float(i)) for i in range(12)]
  m=fit(train,['f'],.00001);test=[dict(run_id='never_seen',f=13.)]
  self.assertAlmostEqual(float(predict(m,test)[0]),3.6,places=4)
  self.assertEqual(m['features'],['f'])

if __name__=='__main__':unittest.main()
