import importlib.util,unittest
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('v2',Path(__file__).with_name('analyze.py'));v2=importlib.util.module_from_spec(spec);spec.loader.exec_module(v2)
class SignalTests(unittest.TestCase):
 def test_derivative_and_gain(self):
  t=np.arange(0,10,.01);v=.1*np.sin(t);a=.07*np.cos(t);vs,ae,ai=v2.derive(t,v,a);m=(t>1)&(t<9)
  np.testing.assert_allclose(ae[m],.1*np.cos(t[m]),atol=.003)
  c,rms=v2.candidate(ae[m],ai[m],.03);self.assertAlmostEqual(c,.7,places=2)
 def test_constant_unobservable(self):
  t=np.arange(0,10,.01);vs,ae,ai=v2.derive(t,t*0+.1,t*0)
  c,rms=v2.candidate(ae[100:-100],ai[100:-100],.03);self.assertIsNone(c)
 def test_delay_sign(self):
  t=np.arange(0,10,.01);a=np.sin(2*t)+.3*np.sin(5*t);imu=np.sin(2*(t-.08))+.3*np.sin(5*(t-.08));m=(t>1)&(t<9)
  self.assertAlmostEqual(v2.lagcheck(t,a,imu,m)['lag_s'],.08,places=2)
if __name__=='__main__':unittest.main()
