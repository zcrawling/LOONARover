"""Full-resolution AprilTag decoding and latest-frame camera acquisition."""
import threading
import time

import cv2 as cv
import numpy as np
from pupil_apriltags import Detector


class ManagedDetector(Detector):
    def __del__(self):
        # post11 frees families before clearing the detector's references to them.
        # Clear those references first to avoid native use-after-free at shutdown.
        ptr = getattr(self, 'tag_detector_ptr', None)
        if ptr:
            self.libc.apriltag_detector_clear_families.argtypes = [type(ptr)]
            self.libc.apriltag_detector_clear_families.restype = None
            self.libc.apriltag_detector_clear_families(ptr)
        super().__del__()


class TagDetector:
    """Decode every measurement; ROI is only a search optimization, never a prediction."""
    def __init__(self, tag_id=0):
        self.tag_id = tag_id
        self.detector = ManagedDetector(families='tag36h11', nthreads=2, quad_decimate=1.,
                                 refine_edges=1, decode_sharpening=.25)
        self.bounds = None
        self.last_full = -float('inf')
        self.margin = None
        self.hamming = None

    def _decode(self, gray):
        image = np.ascontiguousarray(gray)
        found = self.detector.detect(image)
        if not any(t.tag_id == self.tag_id and self._quality(t) for t in found):
            # Mild unsharp masking recovers small blurred cells; corners stay in
            # original pixel coordinates, and decoding quality is still required.
            sharpened = cv.addWeighted(image,2.,cv.GaussianBlur(image,(0,0),1.),-1.,0)
            retry = self.detector.detect(sharpened)
            if any(t.tag_id == self.tag_id and self._quality(t) for t in retry):
                found = retry
        return found

    @staticmethod
    def _quality(tag):
        return tag.hamming <= 1 and tag.decision_margin >= 30

    def detectMarkers(self, frame):
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        now = time.monotonic()
        detections = []
        offset = np.zeros(2)
        if self.bounds is not None and now-self.last_full < 1.:
            x0,y0,x1,y1 = self.bounds
            detections = self._decode(gray[y0:y1,x0:x1])
            offset = np.array([x0,y0])
        if not any(t.tag_id == self.tag_id and self._quality(t) for t in detections):
            detections = self._decode(gray)
            offset = np.zeros(2)
            self.last_full = now
        good = [t for t in detections if self._quality(t)]
        corners = [(t.corners[[1,0,3,2]]+offset).astype(np.float32).reshape(1,4,2) for t in good]
        ids = np.array([[t.tag_id] for t in good],np.int32) if good else None
        self.margin = self.hamming = None
        hits = [i for i,t in enumerate(good) if t.tag_id == self.tag_id]
        if len(hits) == 1:
            i = hits[0]
            self.margin, self.hamming = float(good[i].decision_margin), int(good[i].hamming)
            points = corners[i].reshape(4,2)
            pad = max(60., float(np.ptp(points,axis=0).max()))
            lower = np.maximum(np.floor(points.min(axis=0)-pad),0).astype(int)
            upper = np.minimum(np.ceil(points.max(axis=0)+pad),[gray.shape[1],gray.shape[0]]).astype(int)
            self.bounds = (*lower,*upper)
        else:
            self.bounds = None
        return corners, ids, []


class LatestCapture:
    """Drain V4L2 continuously so detection/encoding cannot queue old camera frames."""
    def __init__(self, cap):
        self.cap = cap
        self.condition = threading.Condition()
        self.stopped = False
        self.sample = None
        self.sequence = 0
        self.consumed = 0
        self.error = None
        self.worker = threading.Thread(target=self._read,daemon=True)
        self.worker.start()

    def _read(self):
        try:
            while not self.stopped:
                started = time.time()
                ok, frame = self.cap.read()
                completed = time.time()
                if not ok:
                    raise RuntimeError('Camera read failed')
                with self.condition:
                    self.sequence += 1
                    self.sample = (frame,started,completed,self.sequence)
                    self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()

    def read(self):
        with self.condition:
            if not self.condition.wait_for(lambda: self.sequence>self.consumed or self.error is not None,timeout=3):
                raise RuntimeError('Camera did not deliver a new frame for 3 seconds')
            if self.error is not None:
                raise self.error
            frame,started,completed,sequence = self.sample
            skipped = sequence-self.consumed-1
            self.consumed = sequence
            return frame,started,completed,skipped

    def close(self):
        self.stopped = True
        self.worker.join(timeout=2)
