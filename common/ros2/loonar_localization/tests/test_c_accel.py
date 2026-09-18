import unittest
import numpy as np
from loonar_localization.c_accel import CConfig,CEstimator,fit_window

class CTests(unittest.TestCase):
    def run_profile(self,c=.7,dec_c=None,gap=False):
        e=CEstimator();dec_c=c if dec_c is None else dec_c
        for t in np.arange(0,10.01,.01):
            if gap and 2.6<t<2.8:continue
            if t<2:phase='STOP';v=0.;acc=0.;stat=True
            elif t<4:phase='ACCEL';v=(t-2)*.125;acc=.125*c;stat=t<2.04
            elif t<5:phase='CRUISE';v=.25;acc=0.;stat=False
            elif t<7:phase='DECEL';v=.25-(t-5)*.125;acc=-.125*dec_c;stat=False
            else:phase='STOP';v=0.;acc=0.;stat=t>8
            r=e.update(float(t),v,acc+.03,0.,0.,phase,stat)
        return e,r
    def test_known_c_and_independent_deceleration(self):
        e,r=self.run_profile()
        self.assertAlmostEqual(e.c_acc,.7,delta=.01);self.assertAlmostEqual(e.c_dec,.7,delta=.01)
        self.assertTrue(r['C_valid']);self.assertFalse(r['C_unreliable'])
    def test_disagreement_and_raw_unclamped(self):
        e,r=self.run_profile(.7,1.2);self.assertTrue(r['C_unreliable']);self.assertFalse(r['C_valid'])
        e,r=self.run_profile(2.5);self.assertGreater(e.c_acc,2.4);self.assertFalse(r['C_valid']);self.assertEqual(r['C_applied'],1.)
    def test_gap_invalidates_run(self):
        e,r=self.run_profile(gap=True);self.assertFalse(r['C_valid']);self.assertTrue(r['C_unreliable'])
    def test_no_excitation(self):
        rows=[(i*.01,.1,0.) for i in range(100)]
        self.assertIsNone(fit_window(rows,CConfig())[0])
    def test_no_bias_invalid_and_yaw_preserved(self):
        e=CEstimator()
        for i in range(100):r=e.update(i*.01,i*.001,.1,.4,.02,'ACCEL',False)
        r=e.update(1.,.1,0.,.4,.02,'CRUISE',False)
        self.assertFalse(r['C_valid']);self.assertEqual(r['pose'][2],.4);self.assertEqual(r['wz'],.02)
    def test_cruise_does_not_fit(self):
        e,r=self.run_profile();a=e.c_acc;d=e.c_dec
        e.update(10.1,.1,3.,0.,0.,'CRUISE',False)
        self.assertEqual(e.c_acc,a);self.assertEqual(e.c_dec,d)

if __name__=='__main__':unittest.main()
