"""Camera-frame XY plot, for tracking inspection rather than base-frame odometry."""
from collections import deque
import cv2 as cv
import numpy as np


class Trajectory:
    def __init__(self):
        self.points = deque(maxlen=10000)

    def show(self, position=None, valid=False):
        if valid and position is not None:
            self.points.append(position[:2].copy())
        canvas = np.full((540, 640, 3), 25, np.uint8)
        cv.putText(canvas, 'Tag position: camera XY (m)', (15, 30),
                   cv.FONT_HERSHEY_SIMPLEX, .6, (230, 230, 230), 1)
        cv.putText(canvas, 'TRACKING' if valid else 'TAG LOST / raw recording continues', (15, 55),
                   cv.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 0) if valid else (0, 150, 255), 1)
        if self.points:
            points = np.asarray(self.points)
            low, high = points.min(axis=0), points.max(axis=0)
            span = max(.2, float((high-low).max()))
            center = (low+high)/2
            pixels = ((points-center)*400/span + [320, 295]).astype(np.int32)
            if len(pixels) > 1:
                cv.polylines(canvas, [pixels.reshape(-1, 1, 2)], False, (100, 210, 255), 2)
            cv.circle(canvas, tuple(pixels[-1]), 5, (0, 255, 0), -1)
            cv.putText(canvas, f'X {points[-1,0]:+.3f}  Y {points[-1,1]:+.3f} | span {span:.2f}m',
                       (15, 520), cv.FONT_HERSHEY_SIMPLEX, .5, (230, 230, 230), 1)
        cv.namedWindow('AprilTag trajectory', cv.WINDOW_NORMAL)
        cv.imshow('AprilTag trajectory', canvas)
