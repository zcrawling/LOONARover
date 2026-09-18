"""Known-transform tests for gyro-fixed yaw correction."""
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from loonar_localization.registration import ICPConfig, StopCorrection, pose_matrix, register, transform
from test_core import corner

class TranslationICPTests(unittest.TestCase):
    def test_lateral_translation_and_tilt_preserve_gyro_yaw(self):
        a = corner()
        actual = pose_matrix([.08, -.06, .3])
        actual[:3, :3] = Rotation.from_euler('xyz', [.04, -.03, .3]).as_matrix()
        actual[2, 3] = .025
        b = transform(np.linalg.inv(actual), a)
        initial = pose_matrix([.12, -.01, .3])
        result = register(a, b, initial)
        self.assertTrue(result['accepted'], result)
        measured = np.array(result['transform'])
        np.testing.assert_allclose(measured, actual, atol=.006)
        self.assertAlmostEqual(Rotation.from_matrix(measured[:3,:3]).as_euler('xyz')[2], .3, places=12)

    def test_wrong_gyro_prior_is_not_silently_corrected(self):
        a = corner(); true = pose_matrix([.03, -.02, .12])
        result = register(a, transform(np.linalg.inv(true), a), pose_matrix([.03, -.02, .10]))
        self.assertAlmostEqual(Rotation.from_matrix(np.array(result['transform'])[:3,:3]).as_euler('xyz')[2], .10, places=12)

    def test_map_translation_correction_preserves_yaw_and_dr_input(self):
        a = corner(); core = StopCorrection()
        core.submit(1, 0., a, [0.,0.,0.], 0.)
        true = pose_matrix([.04,-.06,.3]); b = transform(np.linalg.inv(true),a)
        odom = [.10,0.,.3]; copy = odom.copy()
        result = core.submit(2,1.,b,odom,.1)
        self.assertTrue(result['accepted'],result)
        self.assertEqual(odom,copy)
        np.testing.assert_allclose(core.map_odom[:3,:3],np.eye(3),atol=1e-12)
        np.testing.assert_allclose(core.map_odom@pose_matrix(odom),true,atol=.006)
        # A flat ground patch cannot determine in-plane translation.
        x,y = np.meshgrid(np.linspace(-.8,.8,35),np.linspace(-.8,.8,35))
        plane = np.column_stack([x.ravel(),y.ravel(),np.ones(x.size)])
        self.assertIn('degenerate',register(plane,plane)['reason'])
        saved=core.map_odom.copy();anchor=core.anchor
        rejected=core.submit(3,2.,np.empty((0,3)),[.2,0.,.3],.2)
        self.assertFalse(rejected['accepted']);self.assertIs(core.anchor,anchor)
        np.testing.assert_array_equal(core.map_odom,saved)

if __name__=='__main__':unittest.main()
