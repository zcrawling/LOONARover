"""Replay recorded camera frames without opening a camera, SSH, or motion publisher."""
import argparse
import csv
import json
from pathlib import Path
import cv2 as cv
import numpy as np
from .gt import dictionary,pose
from .tracking import TagDetector
import time
from .run_distance_test import TrackingGate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--detector',choices=['legacy','apriltag'],default='apriltag')
    a=p.parse_args()
    meta=json.loads((a.capture/'capture.json').read_text())
    cal=meta['calibration'];k=np.array(cal['K']);d=np.array(cal['D'])
    with (a.capture/'frames.csv').open() as f:rows=list(csv.DictReader(f))
    detector=TagDetector(meta['tag_id']) if a.detector == 'apriltag' else cv.aruco.ArucoDetector(dictionary(),cv.aruco.DetectorParameters())
    cv.setNumThreads(2)
    detected=0
    durations=[]
    missing_since=None
    longest_missing=0.
    cap=cv.VideoCapture(str(a.capture/'video.avi'))
    prev=origin=initial=None
    gates={axis:TrackingGate() for axis in ['x','y']}
    report={axis:dict(valid=0,invalid=0,events=[],final_distance_m=None,max_lateral_m=0.) for axis in gates}
    modes={axis:None for axis in gates}
    count=0
    for row in rows:
        ok,frame=cap.read()
        if not ok:break
        count+=1
        began=time.perf_counter()
        corners,ids,_=detector.detectMarkers(frame)
        durations.append(time.perf_counter()-began)
        present=ids is not None and np.count_nonzero(ids==meta['tag_id'])==1
        detected+=int(present)
        if present:missing_since=None
        else:
            if missing_since is None:missing_since=float(row['t'])
            longest_missing=max(longest_missing,float(row['t'])-missing_since)
        result=None
        if ids is not None:
            hits=np.flatnonzero(ids.ravel()==meta['tag_id'])
            if len(hits)==1:result=pose(corners[int(hits[0])].reshape(4,2),meta['tag_size'],k,d,prev,meta['max_reprojection_px'])
        for axis in gates:
            valid=False
            if result is not None:
                r,t,error=result
                if error<=meta['max_reprojection_px']:
                    if origin is None:origin,initial=t.copy(),r.copy()
                    direction=initial[:,0 if axis=='x' else 1]
                    distance=float((t-origin)@direction)
                    lateral=float(np.linalg.norm(t-origin-distance*direction))
                    angle=float(np.degrees(np.arccos(np.clip((np.trace(initial.T@r)-1)/2,-1,1))))
                    valid=lateral<=meta['max_lateral_m'] and angle<=meta['max_rotation_deg']
                    report[axis]['max_lateral_m']=max(report[axis]['max_lateral_m'],lateral)
                    if valid:report[axis]['final_distance_m']=distance
            report[axis]['valid' if valid else 'invalid']+=1
            action=gates[axis].update(valid,float(row['t']))
            if action!=modes[axis]:
                report[axis]['events'].append(dict(frame=count-1,action=action))
                modes[axis]=action
        if result is not None and result[2]<=meta['max_reprojection_px']:
            # Use the actual new tracker's acceptance criterion for the X mount.
            r,t,_=result
            v=initial[:,0];s=float((t-origin)@v)
            angle=float(np.degrees(np.arccos(np.clip((np.trace(initial.T@r)-1)/2,-1,1))))
            if angle<=meta['max_rotation_deg'] and np.linalg.norm(t-origin-s*v)<=meta['max_lateral_m']:prev=r.copy()
    cap.release()
    result=dict(detector=a.detector,detected=detected,longest_missing_s=longest_missing,mean_detection_ms=1000*float(np.mean(durations)),frames=count,expected_frames=len(rows),axes=report,note='Offline measurement replay only; no motion executed. Not a full-distance accuracy validation.')
    a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
