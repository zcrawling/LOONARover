import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
import csv
import json
import xml.etree.ElementTree as ET

import cv2 as cv
import numpy as np
from loonar_apriltag.gt import dictionary, objects, pose, prints, track, preview_frame


class GTTests(unittest.TestCase):
    def test_preview_keeps_whole_frame_and_does_not_mutate_input(self):
        frame=np.zeros((1080,1920,3),np.uint8)
        frame[:20,:20]=255
        frame[-20:,-20:]=255
        result=preview_frame(frame)
        self.assertEqual(result.shape,(540,960,3))
        self.assertEqual(frame.shape,(1080,1920,3))
        self.assertEqual(int(result[0,0,0]),255)
        self.assertEqual(int(result[-1,-1,0]),255)
    def test_printed_svg_detects_selected_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            prints(SimpleNamespace(output=tmp,tag_id=0,tag_size=.15,cols=9,rows=6,square_size=.025))
            root = ET.parse(Path(tmp)/'tag36h11.svg').getroot()
            canvas = np.full((950,950),255,np.uint8)
            for r in root.findall('{http://www.w3.org/2000/svg}rect'):
                if r.attrib.get('fill')!='black':continue
                x,y,w,h = [int(round(float(r.attrib[k])*5)) for k in ('x','y','width','height')]
                canvas[y:y+h,x:x+w]=0
            corners,ids,_ = cv.aruco.ArucoDetector(dictionary()).detectMarkers(canvas)
            self.assertEqual(ids.ravel().tolist(),[0])

    def test_metric_pose_and_signed_forward_reverse(self):
        k = np.array([[1000.,0,640],[0,1000,360],[0,0,1.]])
        d = np.zeros(5)
        r = np.array([2.9,.1,.05])
        rotation = cv.Rodrigues(r)[0]
        axis = rotation[:,1]
        p0 = np.array([0.,0.,2.])
        for displacement in (0.,.15,-.15):
            p = p0+displacement*axis
            c,_ = cv.projectPoints(objects(.15),r,p,k,d)
            rr,pp,error = pose(c.reshape(4,2),.15,k,d)
            self.assertLess(error,1e-6)
            np.testing.assert_allclose(pp,p,atol=1e-7)
            self.assertAlmostEqual(float((pp-p0)@axis),displacement,places=6)

    def test_capture_preserves_invalid_frames_and_writes_gt(self):
        k = np.array([[1000.,0,640],[0,1000,360],[0,0,1.]])
        r = np.array([2.9,.1,.05])
        c,_ = cv.projectPoints(objects(.15),r,np.array([0.,0.,2.]),k,np.zeros(5))
        detected = ([c.reshape(1,4,2).astype(np.float32)],np.array([[0]],np.int32),[])
        detector = MagicMock()
        detector.detectMarkers.side_effect = [detected,([],None,[]),detected]
        detector.margin = 50.
        detector.hamming = 0
        capture = MagicMock()
        capture.read.side_effect = [(np.zeros((720,1280,3),np.uint8),1.,1.01,0) for _ in range(3)]
        cap = MagicMock()
        cap.get.return_value = 0.0
        cap.read.side_effect = [(True,np.zeros((720,1280,3),np.uint8)) for _ in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            calibration = Path(tmp)/'cal.json'
            calibration.write_text(json.dumps(dict(K=k.tolist(),D=[0.]*5,width=1280,height=720)))
            a = SimpleNamespace(calibration=str(calibration),output=str(Path(tmp)/'run'),
                func=track,fps=30,duration=0,time_offset_s=0.,tag_size=.15,tag_id=0,
                max_reprojection_px=2,max_rotation_deg=10,max_lateral_m=.1,no_preview=False)
            with patch('loonar_apriltag.gt.camera',return_value=cap), patch('loonar_apriltag.gt.TagDetector',return_value=detector), patch('loonar_apriltag.gt.LatestCapture',return_value=capture), patch('loonar_apriltag.gt.cv.VideoWriter'), patch('loonar_apriltag.gt.show_preview'), patch('loonar_apriltag.gt.cv.waitKey',side_effect=[0,0,ord('q')]), patch('loonar_apriltag.gt.cv.destroyAllWindows'):
                track(a)
            with (Path(a.output)/'gt.csv').open() as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),2)
            self.assertAlmostEqual(float(rows[-1]['s_m']),0.)
            with (Path(a.output)/'frames.csv').open() as f:
                frames=list(csv.DictReader(f))
            self.assertEqual([x['valid'] for x in frames],['1','0','1'])
            self.assertEqual(frames[1]['reason'],'tag_missing')
            cap.release.assert_called_once()

    def test_focus_settling_does_not_start_distance_measurement(self):
        import itertools
        k = np.array([[1000.,0,640],[0,1000,360],[0,0,1.]])
        c,_ = cv.projectPoints(objects(.15),np.array([2.9,.1,.05]),np.array([0.,0.,2.]),k,np.zeros(5))
        detector = MagicMock()
        detector.detectMarkers.return_value = ([c.reshape(1,4,2).astype(np.float32)],np.array([[0]],np.int32),[])
        detector.margin,detector.hamming = 60.,0
        cap = MagicMock()
        cap.get.return_value = 10.
        cap.set.return_value = True
        capture = MagicMock()
        capture.read.return_value = (np.zeros((720,1280,3),np.uint8),1.,1.1,0)
        with tempfile.TemporaryDirectory() as tmp:
            cal = Path(tmp)/'cal.json'
            cal.write_text(json.dumps(dict(K=k.tolist(),D=[0.]*5,width=1280,height=720)))
            a = SimpleNamespace(calibration=str(cal),output=str(Path(tmp)/'run'),func=track,
                fps=30,duration=0,time_offset_s=0.,tag_size=.15,tag_id=0,
                max_reprojection_px=2,max_rotation_deg=10,max_lateral_m=.1,no_preview=False,
                focus_mode='lock',focus=None)
            with patch('loonar_apriltag.gt.camera',return_value=cap), patch('loonar_apriltag.gt.TagDetector',return_value=detector), patch('loonar_apriltag.gt.LatestCapture',return_value=capture), patch('loonar_apriltag.gt.cv.VideoWriter'), patch('loonar_apriltag.gt.show_preview'), patch('loonar_apriltag.gt.cv.destroyAllWindows'), patch('loonar_apriltag.gt.cv.waitKey',side_effect=[0,0,0,ord('q')]), patch('loonar_apriltag.gt.time.monotonic',side_effect=itertools.count(0,.6)):
                track(a)
            rows = list(csv.DictReader((Path(a.output)/'frames.csv').read_text().splitlines()))
            self.assertEqual([r['valid'] for r in rows],['0','0','1','1'])
            self.assertEqual(rows[0]['reason'],'focus_settling')
            gt = list(csv.DictReader((Path(a.output)/'gt.csv').read_text().splitlines()))
            self.assertEqual(len(gt),2)
            cap.set.assert_called_once_with(cv.CAP_PROP_AUTOFOCUS,0)


if __name__=='__main__':unittest.main()
