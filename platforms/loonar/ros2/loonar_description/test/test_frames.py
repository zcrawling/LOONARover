"""Offline TF checks: handedness, user IMU axes, CAD round-trip, joint semantics."""
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
import xacro

PACKAGE=Path(__file__).resolve().parents[1]
PLATFORM=PACKAGE.parents[1]

class Frames(unittest.TestCase):
    def setUp(self):
        self.doc=ET.fromstring(xacro.process_file(str(PACKAGE/'urdf/loonar.urdf.xacro')).toxml())
        self.joints={j.find('child').get('link'):j for j in self.doc.findall('joint')}
    def test_imu_axes(self):
        rpy=list(map(float,self.joints['imu_link'].find('origin').get('rpy').split()))
        R=Rotation.from_euler('xyz',rpy).as_matrix()
        np.testing.assert_allclose(R[:,0],[0,1,0],atol=1e-12)
        np.testing.assert_allclose(R[:,1],[-1,0,0],atol=1e-12)
        np.testing.assert_allclose(R[:,2],[0,0,1],atol=1e-12)
    def test_no_false_motion_or_optical_frames(self):
        links={n.get('name') for n in self.doc.findall('link')}
        self.assertFalse({'odom','map','base_footprint','camera_optical_frame','tof_optical_frame'} & links)
        for side in ('left','right'):
            self.assertEqual(self.joints[side+'_wheel_link'].get('type'),'continuous')
        self.assertEqual(len(links),len(self.joints)+1)
    def test_cad_mount_roundtrip(self):
        config=json.loads((PACKAGE/'config/cad_mounts.json').read_text())
        data=json.loads((PLATFORM/'hardware/tf/cad_frames.json').read_text())
        rows={r['occurrence']:r for r in data['frames'] if r['parent']=='cad_root'}
        T=np.array(config['cad_to_base'])
        for r in config['mounts']:
            j=self.joints[r['name']].find('origin');M=np.eye(4)
            M[:3,3]=list(map(float,j.get('xyz').split()))
            M[:3,:3]=Rotation.from_euler('xyz',list(map(float,j.get('rpy').split()))).as_matrix()
            np.testing.assert_allclose(M,T@np.array(rows[r['source_occurrence']]['root_matrix']),atol=1e-10)
    def test_all_cad_rotations_and_tree(self):
        data=json.loads((PLATFORM/'hardware/tf/cad_frames.json').read_text())
        names={'cad_root'}
        for r in data['frames']:
            self.assertIn(r['parent'],names);self.assertNotIn(r['frame'],names);names.add(r['frame'])
            R=np.array(r['matrix'])[:3,:3]
            np.testing.assert_allclose(R.T@R,np.eye(3),atol=1e-10)
            self.assertAlmostEqual(np.linalg.det(R),1.)
    def test_optical_convention_when_enabled(self):
        doc=ET.fromstring(xacro.process_file(str(PACKAGE/'urdf/loonar.urdf.xacro'),mappings={'publish_optical_frames':'true'}).toxml())
        j=next(j for j in doc.findall('joint') if j.find('child').get('link')=='tof_optical_frame')
        R=Rotation.from_euler('xyz',list(map(float,j.find('origin').get('rpy').split()))).as_matrix()
        np.testing.assert_allclose(R[:,2],[1,0,0],atol=1e-12)
        np.testing.assert_allclose(R[:,0],[0,-1,0],atol=1e-12)

    def test_tof_image_axes_and_lens_datum(self):
        doc=ET.fromstring(xacro.process_file(str(PACKAGE/'urdf/loonar.urdf.xacro'),mappings={'publish_optical_frames':'true'}).toxml())
        joints={j.find('child').get('link'):j for j in doc.findall('joint')}
        def transform(name):
            origin=joints[name].find('origin'); m=np.eye(4)
            m[:3,3]=list(map(float,origin.get('xyz').split()))
            m[:3,:3]=Rotation.from_euler('xyz',list(map(float,origin.get('rpy').split()))).as_matrix()
            return m
        optical=transform('tof_link')@transform('tof_optical_frame')
        # Unrotated raw pixels: right is up, down is robot-right, depth is forward.
        np.testing.assert_allclose(optical[:3,:3],[[0,0,1],[0,-1,0],[1,0,0]],atol=1e-12)
        config=json.loads((PACKAGE/'config/cad_mounts.json').read_text())
        data=json.loads((PLATFORM/'hardware/tf/cad_frames.json').read_text())
        lens=next(r for r in data['frames'] if r['frame']=='cad_root_o19059_o18777_o18760_o18758')
        expected=np.array(config['cad_to_base'])@np.array(lens['root_matrix'])
        np.testing.assert_allclose(optical[:3,3],expected[:3,3],atol=1e-10)
        np.testing.assert_allclose(optical[:3,3],[.05174,.00005,-.0075],atol=1e-10)

    def test_tof_optical_offset_override(self):
        doc=ET.fromstring(xacro.process_file(str(PACKAGE/'urdf/loonar.urdf.xacro'),mappings={'publish_optical_frames':'true','tof_optical_offset':'0.02 0.01 0.03'}).toxml())
        j=next(j for j in doc.findall('joint') if j.find('child').get('link')=='tof_optical_frame')
        self.assertEqual(j.find('origin').get('xyz'),'0.02 0.01 0.03')

if __name__=='__main__':unittest.main()
