import unittest
import math
from .config import limit_motion, wheel_command, CONTROL_GEOMETRY

class SpeedLimitTests(unittest.TestCase):
    def test_translation_and_rotation_saturate(self):
        self.assertEqual(limit_motion(1, 0), (.4, 0))
        self.assertEqual(limit_motion(-1, 0), (-.4, 0))
        self.assertEqual(limit_motion(0, 10), (0, 3.8))
        self.assertEqual(limit_motion(0, -10), (0, -3.8))
        self.assertEqual(limit_motion(.1, .2), (.1, .2))
        self.assertEqual(wheel_command(CONTROL_GEOMETRY, *limit_motion(1, 0)),
                         wheel_command(CONTROL_GEOMETRY, .4, 0))
    def test_combined_motion_preserves_curvature_and_wheel_bound(self):
        for track in (.21, .3):
            for v in (-.4, .4):
                for w in (-3.8, 3.8):
                    a,b = limit_motion(v,w,track)
                    self.assertAlmostEqual(a/b,v/w)
                    self.assertLessEqual(max(abs(a-b*track/2),abs(a+b*track/2)),.40000000001)
    def test_reject_nonfinite(self):
        for v,w in ((math.nan,0),(math.inf,0),(0,math.inf)):
            with self.assertRaises(ValueError): limit_motion(v,w)
