import unittest
import numpy as np
from loonar_localization.core import Config, Estimator, Sample, Primitive, PrimitiveManager, PrimitiveSequence
from loonar_localization.registration import register, ICPConfig, StopCorrection, transform, pose_matrix


def sample(t, v=0., w=0., wz=0., ax=0.):
    return Sample(t,v,w,np.array([0.,0.,wz]),np.array([ax,0.,9.81]))


def corner():
    rng=np.random.default_rng(5); p=rng.uniform(-.8,.8,(2500,3))
    for k in range(3): p[k::3,k]=[1.,1.2,.8][k]
    return p


class Tests(unittest.TestCase):
    def test_v1_identical_integration_and_no_hard_rotate_translation(self):
        e=Estimator(Config(stationary_enabled=False))
        for t in np.arange(0,2.001,.01):r=e.update(sample(t,.1,.4,.2),Primitive.ROTATE_LEFT)
        self.assertAlmostEqual(r['pose'][2],.4,places=10)
        self.assertAlmostEqual(r['encoder_pose'][2],.8,places=10)
        self.assertGreater(r['pose'][0],.19)
        self.assertEqual(r['vx'],.1)
        self.assertLessEqual(r['confidence'],.3)
        self.assertFalse(r['acceleration_valid'])
        self.assertIsNone(r['longitudinal_score'])

    def test_stop_command_is_not_stationary(self):
        for moving in [dict(v=.1),dict(wz=.1),dict(ax=1.)]:
            e=Estimator()
            for i,t in enumerate(np.arange(0,2,.02)):
                kw=dict(moving)
                if 'ax' in kw:kw['ax']*=(-1)**i
                r=e.update(sample(t,**kw),Primitive.STOP)
            self.assertFalse(r['stationary'])

    def test_command_is_prior_not_stationary_truth(self):
        e=Estimator()
        for t in np.arange(0,2,.02):r=e.update(sample(t),Primitive.STRAIGHT_NORMAL)
        self.assertTrue(r['stationary'])
        self.assertEqual(r['stationary_reason'],'sensor_window_stationary_command_conflict')

    def test_static_bias_and_continuity(self):
        e=Estimator(Config(bias_tau=.1))
        for t in np.arange(0,3,.02):r=e.update(sample(t,wz=.01),Primitive.STOP)
        self.assertTrue(r['stationary']);self.assertEqual(r['wz'],0)
        self.assertAlmostEqual(r['bias'][2],.01,places=6)
        self.assertGreater(r['pose'][2],0) # no retrospective pose reset

    def test_gap_and_timestamp_rejection(self):
        e=Estimator();e.update(sample(0,.1));r=e.update(sample(5,.1))
        self.assertEqual(r['pose'],[0.,0.,0.]);self.assertFalse(r['stationary'])
        self.assertIn('sensor_gap_no_integration',r['reasons'])
        with self.assertRaises(ValueError):e.update(sample(4))

    def test_primitive_plan_and_curves(self):
        p=PrimitiveManager();self.assertEqual(p.observe(.1,.1),Primitive.UNKNOWN)
        self.assertEqual([x[0] for x in p.plan(-.5,1.)],[Primitive.ROTATE_RIGHT,Primitive.STOP,Primitive.STRAIGHT_NORMAL,Primitive.STOP])

    def test_feedback_primitive_sequence(self):
        q=PrimitiveSequence();q.start(.5,1.)
        state=dict(pose=[0.,0.,0.],stationary=False)
        self.assertEqual(q.update(state)['primitive'],'STOP')
        state['stationary']=True
        self.assertEqual(q.update(state)['primitive'],'ROTATE_LEFT')
        state.update(pose=[0.,0.,.5],stationary=False)
        self.assertEqual(q.update(state)['primitive'],'STOP')
        self.assertEqual(q.update(state)['reason'],'await_stationary')
        state['stationary']=True
        self.assertEqual(q.update(state)['primitive'],'STRAIGHT_NORMAL')
        state.update(pose=[np.cos(.5),np.sin(.5),.5],stationary=False)
        self.assertEqual(q.update(state)['primitive'],'STOP')
        state['stationary']=True
        self.assertTrue(q.update(state)['complete'])

    def test_plane_rejected(self):
        x,y=np.meshgrid(np.linspace(-1,1,30),np.linspace(-1,1,30));p=np.column_stack([x.ravel(),y.ravel(),np.ones(x.size)])
        r=register(p,p)
        self.assertFalse(r['accepted']);self.assertIn('degenerate',r['reason'])

    def test_stuck_evidence_requires_accepted_geometry(self):
        p=corner();c=StopCorrection();c.submit(1,0,p,[0.,0.,0.],0.)
        r=c.submit(2,2,p,[.08,0.,0.],.2)
        self.assertTrue(r['accepted'],r)
        self.assertEqual(r['state'],'STUCK_SUSPECT')
        before=c.map_odom.copy();anchor=c.anchor
        plane=p.copy();plane[:,2]=1.
        r=c.submit(3,3,plane,[.09,0.,0.],.3)
        self.assertFalse(r['accepted']);self.assertIs(c.anchor,anchor)
        np.testing.assert_array_equal(c.map_odom,before)

    def test_monitor_disables_nhc_without_scaling_velocity(self):
        e=Estimator()
        for t in np.arange(0,2,.02):r=e.update(sample(t,.1,.5,0.),Primitive.STRAIGHT_NORMAL)
        self.assertEqual(r['state'],'DEGRADED');self.assertEqual(r['nhc_weight'],0)
        self.assertEqual(r['vx'],.1)
        for t in np.arange(2,5,.02):r=e.update(sample(t,.1,0.,0.),Primitive.STRAIGHT_NORMAL)
        self.assertEqual(r['state'],'VALID');self.assertGreater(r['nhc_weight'],0)
        self.assertFalse(r['nhc_applied'])

    def test_corner_pose_and_anchor_preservation(self):
        A=corner();T=pose_matrix([.04,-.03,.03]);B=transform(np.linalg.inv(T),A)
        r=register(A,B,config=ICPConfig(mode='full_6d'))
        self.assertTrue(r['accepted'],r)
        np.testing.assert_allclose(r['transform'],T,atol=.005)
        c=StopCorrection();c.submit(1,0,A,[0.,0.,0.],0.)
        old=c.anchor;r=c.submit(2,1,np.zeros((10,3)),[.1,0.,0.],.1)
        self.assertFalse(r['accepted']);self.assertIs(c.anchor,old)
        r=c.submit(3,2,B,[.08,0.,.03],.08)
        self.assertTrue(r['accepted'],r)
        np.testing.assert_allclose(c.map_odom@pose_matrix([.08,0.,.03]),T,atol=.005)
        self.assertEqual(c.submit(3,2,B,[.08,0.,.03],.08)['reason'],'already_processed_stop')

if __name__=='__main__':unittest.main()
