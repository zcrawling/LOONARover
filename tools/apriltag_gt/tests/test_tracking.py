import threading
import unittest
from unittest.mock import patch
import cv2 as cv
import numpy as np
from loonar_apriltag.tracking import TagDetector, LatestCapture


class TrackingTests(unittest.TestCase):
    def test_decode_corner_order_roi_reacquisition_and_blank(self):
        dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_APRILTAG_36h11)
        marker = cv.aruco.generateImageMarker(dictionary, 0, 100)
        detector = TagDetector()
        for x in (100,110,650):
            frame = np.full((400,900),255,np.uint8)
            frame[120:220,x:x+100] = marker
            corners,ids,_ = detector.detectMarkers(frame)
            self.assertEqual(ids.ravel().tolist(),[0])
            np.testing.assert_allclose(corners[0].reshape(4,2),
                [[x,120],[x+100,120],[x+100,220],[x,220]],atol=1.5)
            self.assertEqual(detector.hamming,0)
        self.assertIsNone(detector.detectMarkers(np.full((400,900),255,np.uint8))[1])

    def test_latest_capture_reports_skips_and_original_timestamps(self):
        ready = threading.Event()
        release = threading.Event()
        class Camera:
            count = 0
            def read(self):
                self.count += 1
                if self.count == 4:
                    ready.set()
                    release.wait(2)
                return True, np.full((2,2),self.count,np.uint8)
        capture = LatestCapture(Camera())
        try:
            self.assertTrue(ready.wait(2))
            frame,started,completed,skipped = capture.read()
            self.assertEqual(int(frame[0,0]),3)
            self.assertEqual(skipped,2)
            self.assertLessEqual(started,completed)
        finally:
            capture.stopped = True
            release.set()
            capture.close()
