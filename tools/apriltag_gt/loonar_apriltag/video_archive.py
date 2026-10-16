"""Archive camera reads before best-effort live detection; no motion or ROS imports."""
import csv

import cv2 as cv


class VideoArchive:
    def __init__(self, directory, width, height, fps):
        self.width, self.height, self.fps = width, height, fps
        self.directory = directory
        self.writer = None
        self.file = (directory / 'video_frames.csv').open('x')
        self.rows = csv.writer(self.file)
        self.rows.writerow(['frame', 'read_started_epoch', 'read_completed_epoch',
                            'receipt_monotonic_ns'])
        self.file.flush()

    def __call__(self, frame, started, completed, index, receipt_monotonic_ns):
        if frame.shape[:2] != (self.height, self.width):
            raise ValueError('Capture resolution differs from calibration')
        if self.writer is None:
            self.writer = cv.VideoWriter(str(self.directory / 'video.avi'),
                cv.VideoWriter_fourcc(*'MJPG'), self.fps, (self.width, self.height))
            if not self.writer.isOpened():
                raise RuntimeError('Cannot create raw video archive')
        self.writer.write(frame)
        self.rows.writerow([index, f'{started:.9f}', f'{completed:.9f}', receipt_monotonic_ns])
        self.file.flush()

    def close(self):
        if self.writer is not None:
            self.writer.release()
        self.file.close()
