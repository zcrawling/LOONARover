import unittest
from types import SimpleNamespace
import numpy as np
from analyze import integrate,aligned,ranges

class OfflineTests(unittest.TestCase):
 def test_straight_and_reverse(self):
  t=np.linspace(0,10,1001)
  for speed in [.1,-.1]:
   p=integrate(t,np.full_like(t,speed),np.zeros_like(t))
   np.testing.assert_allclose(p[-1],[speed*10,0,0],atol=1e-12)
 def test_curved_motion(self):
  t=np.linspace(0,10,1001);w=.15;v=.1;p=integrate(t,np.full_like(t,v),np.full_like(t,w))
  np.testing.assert_allclose(p[-1],[v/w*np.sin(1.5),v/w*(1-np.cos(1.5)),1.5],atol=1e-6)
 def test_header_alignment_bias_and_gap(self):
  t=np.arange(0,3,.01);keep=(t<1)|(t>1.2);ti=t[keep];bias=.02
  imu=np.column_stack([ti,ti*0,ti*0,ti*0+bias,ti+.003]);wheel=np.column_stack([t,np.zeros((len(t),5)),t+.005])
  data=dict(im=imu,w=wheel,cmd=np.array([[0,0,0]]));args=SimpleNamespace(gyro_delay=0,hz=100,static_v=.005,static_w=.01,static_trim=.2,min_static_seconds=.3)
  tt,w,g,valid,static,cmd=aligned(data,args)
  self.assertEqual(len(ranges(valid)),2);self.assertTrue(static.any())
  b=np.mean(g[static]);self.assertAlmostEqual(b,bias)
  for a,z in ranges(valid):
   p=integrate(tt[a:z],w[a:z,0],g[a:z]-b)
   np.testing.assert_allclose(p,0,atol=1e-12)
if __name__=='__main__':unittest.main()
