import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcu_v2.imu_pair import ImuPair
from c_acc.profile import cruise_duration,velocity

class PortTests(unittest.TestCase):
    def test_pair_same_burst(self):
        p=ImuPair()
        self.assertIsNone(p.add(2,100,[1,2,3]))
        self.assertEqual(p.add(4,100,[4,5,6]),((1,2,3),(4,5,6)))
        self.assertIsNone(p.add(4,100,[4,5,6]))
    def test_never_pair_different_bursts(self):
        p=ImuPair();p.add(2,100,[1,2,3])
        self.assertIsNone(p.add(4,101,[4,5,6]))
        self.assertIsNone(p.add(2,102,[1,2,3]))
        self.assertIsNone(p.add(4,102,[math.nan,0,0]))
    def test_order_independent(self):
        p=ImuPair();p.add(4,10,[0,1,2]);self.assertEqual(p.add(2,10,[0,0,0]),((0,0,0),(0,1,2)))
    def test_distance(self):
        c=cruise_duration(.25,2.5,2.,2.5,4.,1.)
        self.assertAlmostEqual(c,1.5)
        self.assertAlmostEqual(.25*(2.5+c),1.)
    def test_reject_impossible_and_nonfinite(self):
        for d in (.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):cruise_duration(.25,2.5,2.,2.5,4.,d)
    def test_phase_boundaries(self):
        self.assertEqual(velocity(0,.25,2.5,1.5,2.5),('ACCEL',0.))
        self.assertEqual(velocity(2.5,.25,2.5,1.5,2.5),('CRUISE',.25))
        self.assertEqual(velocity(4,.25,2.5,1.5,2.5),('DECEL',.25))
        self.assertEqual(velocity(6.5,.25,2.5,1.5,2.5),('STOP',0.))

if __name__=='__main__':unittest.main()
