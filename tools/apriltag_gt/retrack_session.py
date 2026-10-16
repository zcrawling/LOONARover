"""Re-track every archived manual-session frame, using its mapped Pi timestamp."""
import argparse
import csv
import json
from pathlib import Path
import time

import cv2 as cv
import numpy as np
from loonar_apriltag.gt import pose, show_preview
from loonar_apriltag.tracking import TagDetector
from loonar_apriltag.trajectory import Trajectory
from loonar_apriltag.session_time import align_session


def retrack(session, output, preview=True, max_error=2.):
    session, output = Path(session), Path(output)
    align_session(session)
    meta = json.loads((session/'camera/capture.json').read_text())
    calibration = meta['calibration']
    k, d = np.asarray(calibration['K']), np.asarray(calibration['D'])
    detector = TagDetector(meta['tag_id'])
    cap = cv.VideoCapture(str(session/'camera/video.avi'))
    if not cap.isOpened():
        raise ValueError('Cannot open archived video')
    output.mkdir(parents=True, exist_ok=False)
    previous = None
    count = accepted = 0
    complete = False
    trajectory = Trajectory()
    report = dict(source_session=str(session.resolve()), time_domain='Pi CLOCK_REALTIME',
        pose_definition='camera-to-tag translation metres and rotation matrix; not base-frame or floor-map pose',
        exposure_latency_calibrated=False, max_reprojection_px=max_error)
    try:
        with (session/'timestamps.csv').open() as timing, (output/'poses.csv').open('w') as file:
            fields = ['video_frame', 'pi_epoch', 'laptop_receipt_epoch', 'clock_rtt_half_s',
                      'clock_step', 'valid', 'reason', 'x', 'y', 'z', 'reprojection_px',
                      'decision_margin', 'hamming', *[f'r{i}{j}' for i in range(3) for j in range(3)]]
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for stamp in csv.DictReader(timing):
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f'Video ended before timestamp row {stamp["video_frame"]}')
                if int(stamp['video_frame']) != count:
                    raise ValueError('Frame mapping is not contiguous')
                if frame.shape[:2] != (calibration['height'], calibration['width']):
                    raise ValueError('Video resolution differs from calibration')
                corners, ids, _ = detector.detectMarkers(frame)
                result = None
                reason = 'tag_missing'
                if ids is not None:
                    hits = np.flatnonzero(ids.ravel() == meta['tag_id'])
                    if len(hits) == 1:
                        result = pose(corners[int(hits[0])].reshape(4, 2), meta['tag_size'],
                                      k, d, previous, max_error)
                        reason = 'pose_failed' if result is None else 'reprojection_error'
                    else:
                        reason = 'wrong_id_or_duplicate'
                valid = result is not None and result[2] <= max_error
                row = {key: stamp[key] for key in fields if key in stamp}
                row.update(valid=int(valid), reason='ok' if valid else reason,
                           decision_margin=detector.margin, hamming=detector.hamming)
                if result is not None:
                    r, position, error = result
                    row.update(x=position[0], y=position[1], z=position[2], reprojection_px=error)
                    row.update({f'r{i}{j}': r[i,j] for i in range(3) for j in range(3)})
                    if valid:
                        previous = r.copy()
                writer.writerow(row)
                count += 1
                accepted += int(valid)
                if preview:
                    if ids is not None:
                        cv.aruco.drawDetectedMarkers(frame, corners, ids)
                    cv.putText(frame, f'frame {count-1} | Pi {stamp["pi_epoch"]} | {row["reason"]}',
                               (10, 30), cv.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 0), 1)
                    show_preview('AprilTag replay - q to finish', frame)
                    trajectory.show(result[1] if result is not None else None, valid)
                    if cv.waitKey(1) & 255 == ord('q'):
                        break
            else:
                ok, _ = cap.read()
                if ok:
                    raise ValueError('Video contains frames without timestamp rows')
                complete = True
    finally:
        cap.release()
        if preview:
            cv.destroyAllWindows()
        report.update(frames=count, valid=accepted, complete=complete)
        (output/'tracking.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('session', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--no-preview', action='store_true')
    p.add_argument('--max-reprojection-px', type=float, default=2.)
    a = p.parse_args()
    if not np.isfinite(a.max_reprojection_px) or a.max_reprojection_px <= 0:
        p.error('max-reprojection-px must be finite and positive')
    output = a.output or a.session/('tracking_'+time.strftime('%Y%m%d_%H%M%S'))
    print(json.dumps(retrack(a.session, output, not a.no_preview, a.max_reprojection_px), indent=2))


if __name__ == '__main__':
    main()
