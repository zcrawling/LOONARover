"""Fixed USB camera, calibrated AprilTag 36h11 tracking for straight-run GT."""
import argparse
import csv
import json
from pathlib import Path
import time

import cv2 as cv
import numpy as np
from .tracking import TagDetector, LatestCapture


def dictionary():
    return cv.aruco.getPredefinedDictionary(cv.aruco.DICT_APRILTAG_36h11)


def objects(size):
    h = size / 2
    return np.array([[-h,h,0],[h,h,0],[h,-h,0],[-h,-h,0]], np.float64)


def pose(corners, size, k, d, previous=None, max_error=2.):
    ok, rotations, translations, _ = cv.solvePnPGeneric(objects(size), corners, k, d, flags=cv.SOLVEPNP_IPPE_SQUARE)
    if not ok:
        return None
    candidates = []
    for r,t in zip(rotations,translations):
        if t[2,0]<=0:continue
        projected, _ = cv.projectPoints(objects(size), r, t, k, d)
        error = float(np.sqrt(np.mean(np.sum((projected.reshape(4,2)-corners)**2, axis=1))))
        candidates.append((cv.Rodrigues(r)[0],t.ravel(),error))
    if not candidates:return None
    eligible = [c for c in candidates if c[2]<=max_error]
    if previous is not None and eligible:
        return min(eligible,key=lambda c: np.arccos(np.clip((np.trace(previous.T@c[0])-1)/2,-1,1)))
    return min(candidates,key=lambda c:c[2])


def prints(a):
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    marker = cv.aruco.generateImageMarker(dictionary(), a.tag_id, 800)
    # Native SVG has exact mm units; black border edge is the specified size.
    cells = cv.resize(marker, (8,8), interpolation=cv.INTER_NEAREST)
    def svg(name, width, height, body):
        (out/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>{body}</svg>')
    mm = a.tag_size*1000
    body = ''.join(f'<rect x="{20+x*mm/8}" y="{20+y*mm/8}" width="{mm/8}" height="{mm/8}" fill="black"/>' for y in range(8) for x in range(8) if cells[y,x] == 0)
    body += f'<text x="{(mm+40)/2}" y="7" text-anchor="middle" font-size="4">FORWARD / tag +Y</text>'
    body += f'<text x="{(mm+40)/2}" y="{mm+35}" text-anchor="middle" font-size="4">36h11 ID {a.tag_id} | black edge {mm:g} mm | print 100%</text>'
    svg('tag36h11.svg', mm+40, mm+40, body)
    sq = a.square_size*1000
    body = ''.join(f'<rect x="{10+x*sq}" y="{10+y*sq}" width="{sq}" height="{sq}" fill="black"/>' for y in range(a.rows+1) for x in range(a.cols+1) if (x+y)%2 == 0)
    svg('checkerboard.svg', (a.cols+1)*sq+20, (a.rows+1)*sq+20, body)
    print(f'Print at 100%, no fit-to-page. Tag black outer edge {mm} mm; checker square {sq} mm.')


def camera(a):
    cap = cv.VideoCapture(a.camera, cv.CAP_V4L2)
    cap.set(cv.CAP_PROP_FOURCC,cv.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv.CAP_PROP_FRAME_WIDTH, a.width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, a.height)
    cap.set(cv.CAP_PROP_FPS, a.fps)
    cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise ValueError('Cannot open camera')
    focus = getattr(a, 'focus', None)
    if focus is not None:
        if not cap.set(cv.CAP_PROP_AUTOFOCUS, 0) or not cap.set(cv.CAP_PROP_FOCUS, focus):
            cap.release()
            raise ValueError('Camera rejected manual focus; check C920 controls')
    elif getattr(a, 'focus_mode', 'keep') == 'lock':
        if not cap.set(cv.CAP_PROP_AUTOFOCUS, 1):
            print('Autofocus control unavailable; retaining camera focus.', flush=True)
    actual = dict(device=a.camera,width=int(cap.get(cv.CAP_PROP_FRAME_WIDTH)),
                  height=int(cap.get(cv.CAP_PROP_FRAME_HEIGHT)),fps=cap.get(cv.CAP_PROP_FPS),
                  focus=cap.get(cv.CAP_PROP_FOCUS),autofocus=cap.get(cv.CAP_PROP_AUTOFOCUS),
                  zoom=cap.get(cv.CAP_PROP_ZOOM))
    print('Camera negotiated settings (unsupported controls may report 0): '+json.dumps(actual),flush=True)
    return cap


def preview_frame(frame, width=960, height=540):
    """Fit the whole image for display only; no crop or calibration coordinate change."""
    ratio = min(width/frame.shape[1], height/frame.shape[0], 1.)
    return cv.resize(frame,(max(1,round(frame.shape[1]*ratio)),max(1,round(frame.shape[0]*ratio))),interpolation=cv.INTER_AREA)


def show_preview(title, frame):
    view = preview_frame(frame)
    cv.namedWindow(title,cv.WINDOW_NORMAL | cv.WINDOW_KEEPRATIO)
    cv.imshow(title,view)


def inspect_camera(a):
    """Camera/tag diagnosis only: no pose calibration needed and no rover connection."""
    cap = camera(a)
    detector = TagDetector(getattr(a, "tag_id", 0))
    print('Camera-only inspection. q exits; no driving or ROS commands.',flush=True)
    try:
        while True:
            ok,frame = cap.read()
            if not ok:raise ValueError('Camera read failed')
            corners,ids,rejected = detector.detectMarkers(frame)
            if ids is not None:cv.aruco.drawDetectedMarkers(frame,corners,ids)
            text = f'{frame.shape[1]}x{frame.shape[0]} | 36h11 IDs={[] if ids is None else ids.ravel().tolist()} | candidates={len(rejected)}'
            cv.putText(frame,text,(15,35),cv.FONT_HERSHEY_SIMPLEX,.8,(0,255,0),2)
            show_preview('Camera only - no motion - q exits',frame)
            if cv.waitKey(1)&255==ord('q'):break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv.destroyAllWindows()


def calibrate(a):
    if Path(a.output).exists():
        raise ValueError(f'Output already exists: {a.output}; choose a new filename')
    print(f'Checkerboard: {a.cols} x {a.rows} inner corners, square {a.square_size*1000:g} mm')
    world = np.zeros((a.cols*a.rows,3), np.float32)
    world[:,:2] = np.mgrid[0:a.cols,0:a.rows].T.reshape(-1,2)*a.square_size
    points, images = [], []
    size = None
    if a.images:
        files = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp','.tif','.tiff'))
        accepted, rejected = [], []
        for path in files:
            frame = cv.imread(str(path))
            if frame is None:
                raise ValueError(f'Cannot read {path}')
            current = (frame.shape[1],frame.shape[0])
            if size is not None and current != size:
                raise ValueError('Images have different resolutions')
            size = current
            found, corners = cv.findChessboardCornersSB(cv.cvtColor(frame,cv.COLOR_BGR2GRAY), (a.cols,a.rows), flags=cv.CALIB_CB_EXHAUSTIVE | cv.CALIB_CB_ACCURACY)
            print(f'{"OK" if found else "NOT FOUND"}: {path.name}',flush=True)
            if found:
                images.append(corners)
                points.append(world.copy())
                accepted.append(str(path.resolve()))
            else:
                rejected.append(str(path.resolve()))
        save_calibration(a,points,images,size,accepted,rejected)
        return
    print('SPACE: capture detected board; q: finish after at least 15 varied views.')
    cap = camera(a)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Camera read failed')
            size = (frame.shape[1], frame.shape[0])
            found, corners = cv.findChessboardCornersSB(cv.cvtColor(frame,cv.COLOR_BGR2GRAY), (a.cols,a.rows))
            if found:
                cv.drawChessboardCorners(frame,(a.cols,a.rows),corners,found)
            cv.putText(frame,f'{len(images)} views | SPACE capture | q finish',(15,30),cv.FONT_HERSHEY_SIMPLEX,.6,(0,255,0),2)
            show_preview('Calibration',frame)
            key = cv.waitKey(1)&255
            if key == 32 and found:
                images.append(corners.copy())
                points.append(world.copy())
            if key == ord('q'):
                break
    finally:
        cap.release()
        cv.destroyAllWindows()
    save_calibration(a,points,images,size)


def save_calibration(a,points,images,size,accepted=None,rejected=None):
    if len(images) < 15:
        raise ValueError('Need at least 15 varied views: corners, centre, tilt and distance')
    rms,k,d,r,t = cv.calibrateCamera(points,images,size,None,None)
    errors = []
    for obj,img,rv,tv in zip(points,images,r,t):
        p,_ = cv.projectPoints(obj,rv,tv,k,d)
        errors.append(float(np.sqrt(np.mean(np.sum((p-img)**2,axis=2)))))
    with open(a.output,'x') as f:
        json.dump(dict(width=size[0],height=size[1],K=k.tolist(),D=d.tolist(),rms_px=rms,view_errors_px=errors,views=len(images),square_size_m=a.square_size,inner_cols=a.cols,inner_rows=a.rows,source_images=accepted,rejected_images=rejected),f,indent=2)
    print(f'fx={k[0,0]:.3f}, fy={k[1,1]:.3f}, cx={k[0,2]:.3f}, cy={k[1,2]:.3f} pixels')
    print(f'Distortion [k1, k2, p1, p2, k3]: {d.ravel().tolist()}')
    print(f'Saved calibration; RMS={rms:.3f}px. Verify scale with a measured translation before GT use.')


def track(a):
    calibration = json.loads(Path(a.calibration).read_text())
    k,d = np.array(calibration['K']),np.array(calibration['D'])
    detector = TagDetector(getattr(a, "tag_id", 0))
    out = Path(a.output)
    out.mkdir(parents=True,exist_ok=False)
    meta = vars(a).copy()
    meta.pop('func')
    meta.update(timestamp='host receipt epoch + measured offset; NOT hardware exposure time',
                gt_definition=('full camera-to-tag rotation/translation; s_m is initial-axis projection, not path distance' if getattr(a,'free_motion',False) else 'signed projection on configured initial tag axis; straight runs only'),
                verified_for_training=False, calibration=calibration,
                detector=dict(backend='pupil-apriltags',family='tag36h11',quad_decimate=1,
                              max_hamming=1,min_decision_margin=30,roi_full_resolution=True,
                              sharpen_retry=True))
    (out/'capture.json').write_text(json.dumps(meta,indent=2))
    cap = camera(a)
    origin = axis = rotation0 = previous_rotation = None
    meta['camera_readback'] = {name: cap.get(prop) for name,prop in [
        ('width',cv.CAP_PROP_FRAME_WIDTH),('height',cv.CAP_PROP_FRAME_HEIGHT),
        ('fps',cv.CAP_PROP_FPS),('autofocus',cv.CAP_PROP_AUTOFOCUS),
        ('focus',cv.CAP_PROP_FOCUS),('auto_exposure',cv.CAP_PROP_AUTO_EXPOSURE),
        ('exposure',cv.CAP_PROP_EXPOSURE)]}
    meta['camera_readback_note'] = 'Backend readback only; unsupported properties may return zero. Focus policy recorded in focus_mode/focus; exposure retained. Automatic focus locks after continuous tag decoding.'
    (out/'capture.json').write_text(json.dumps(meta,indent=2))
    focus_since = None
    last_focus = None
    focus_locked = getattr(a, "focus", None) is not None or getattr(a, "focus_mode", "keep") == "keep"
    capture = LatestCapture(cap)
    last_s = 0.
    writer_video = None
    began = time.monotonic()
    try:
        with (out/'gt.csv').open('w') as f, (out/'frames.csv').open('w') as log:
            gt = csv.writer(f); gt.writerow(['t','s_m'])
            rows = csv.writer(log); rows.writerow(['frame','t','valid','reason','x','y','z','s_m','reprojection_px','heading_change_deg','read_started_epoch','read_completed_epoch','detection_completed_epoch','skipped_capture_frames','decision_margin','hamming',*[f'r{i}{j}' for i in range(3) for j in range(3)]])
            index = 0
            while not a.duration or time.monotonic()-began < a.duration:
                frame, read_started, read_completed, skipped = capture.read()
                timestamp = read_completed+a.time_offset_s
                if frame.shape[:2] != (calibration['height'],calibration['width']):
                    raise ValueError('Capture resolution differs from calibration; recalibrate at this resolution')
                if writer_video is None:
                    writer_video = cv.VideoWriter(str(out/'video.avi'),cv.VideoWriter_fourcc(*'MJPG'),a.fps,(frame.shape[1],frame.shape[0]))
                    if not writer_video.isOpened():
                        raise ValueError('Cannot create video')
                writer_video.write(frame)  # Unannotated video, exact frame-to-time mapping in frames.csv.
                corners,ids,rejected = detector.detectMarkers(frame)
                result = None
                reason = 'tag_missing'
                if ids is not None:
                    hits = np.flatnonzero(ids.ravel()==a.tag_id)
                    if len(hits)==1:
                        result = pose(corners[int(hits[0])].reshape(4,2),a.tag_size,k,d,previous_rotation,a.max_reprojection_px)
                        if result is None:reason = 'pose_failed'
                    else:
                        reason = 'wrong_id_or_duplicate'
                    cv.aruco.drawDetectedMarkers(frame,corners,ids)
                valid = False
                values = ['']*6
                rotation_values = ['']*9
                if result is not None:
                    rotation, position, error = result
                    rotation_values = rotation.ravel().tolist()
                    reason = 'reprojection_error'
                    if error <= a.max_reprojection_px:
                        if origin is None:
                            direction = getattr(a,'forward_axis','y')
                            axis = rotation[:,0 if direction.lstrip('-')=='x' else 1].copy()
                            if direction.startswith('-'):axis *= -1
                            origin,rotation0 = position.copy(),rotation.copy()
                        angle = float(np.degrees(np.arccos(np.clip((np.trace(rotation0.T@rotation)-1)/2,-1,1))))
                        s = float((position-origin)@axis)
                        lateral = float(np.linalg.norm(position-origin-s*axis))
                        valid = getattr(a,'free_motion',False) or (angle <= a.max_rotation_deg and lateral <= a.max_lateral_m)
                        reason = 'ok' if valid else 'outside_straight_run_assumption'
                        values = [*position,s,error,angle]
                        if valid:
                            previous_rotation = rotation.copy()
                            if focus_locked:
                                gt.writerow([f'{timestamp:.9f}',s]); f.flush()
                            last_s = s
                if not focus_locked:
                    current_focus = cap.get(cv.CAP_PROP_FOCUS)
                    if last_focus is not None and current_focus != last_focus:
                        focus_since = None
                    last_focus = current_focus
                    if valid:
                        if focus_since is None: focus_since = time.monotonic()
                        if time.monotonic()-focus_since >= 1.:
                            focus_locked = bool(cap.set(cv.CAP_PROP_AUTOFOCUS, 0))
                            meta['focus_lock'] = dict(success=focus_locked, epoch=time.time(),
                                focus=cap.get(cv.CAP_PROP_FOCUS), autofocus=cap.get(cv.CAP_PROP_AUTOFOCUS))
                            (out/'capture.json').write_text(json.dumps(meta,indent=2))
                            print('Focus lock: '+json.dumps(meta['focus_lock']),flush=True)
                            if not focus_locked:
                                raise ValueError('Camera rejected autofocus lock; use --focus-mode keep to retain current controls')
                    else:
                        focus_since = None
                    # Establish the distance origin only after optics have settled.
                    origin = axis = rotation0 = previous_rotation = None
                    valid = False
                    reason = 'focus_settling'
                rows.writerow([index,f'{timestamp:.9f}',int(valid),reason,*values,read_started,read_completed,time.time(),skipped,detector.margin,detector.hamming,*rotation_values]); log.flush()
                index += 1
                if not a.no_preview:
                    cv.putText(frame,f'{reason} | signed distance {last_s:.3f} m',(10,30),cv.FONT_HERSHEY_SIMPLEX,.6,(0,255,0),2)
                    cv.putText(frame,f'{frame.shape[1]}x{frame.shape[0]} | IDs={[] if ids is None else ids.ravel().tolist()} | margin={detector.margin} | bit corrections={detector.hamming}',(10,65),cv.FONT_HERSHEY_SIMPLEX,.6,(0,255,0),2)
                    show_preview('AprilTag GT - q to finish',frame)
                    if cv.waitKey(1)&255 == ord('q'):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        capture.close()
        cap.release()
        if writer_video is not None:
            writer_video.release()
        cv.destroyAllWindows()
    print(f'Saved {out}. Validate timing and distance before using gt.csv for training.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(required=True)
    def board(q):
        q.add_argument('--cols',type=int,default=9,help='Inner corners horizontally')
        q.add_argument('--rows',type=int,default=6,help='Inner corners vertically')
        units = q.add_mutually_exclusive_group()
        units.add_argument('--square-size',type=float,default=.025,help='Square side in metres (default: 0.025)')
        units.add_argument('--square-size-mm',type=float,help='Measured square side in millimetres, e.g. 25 or 24.8')
    def tag(q):
        q.add_argument('--tag-id',type=int,default=0)
        q.add_argument('--tag-size',type=float,default=.15,help='Measured black outer edge in metres')
    def cam(q):
        q.add_argument('--camera',default='/dev/video0')
        q.add_argument('--width',type=int,default=1280)
        q.add_argument('--height',type=int,default=720)
        q.add_argument('--fps',type=float,default=30)
        q.add_argument('--focus-mode',choices=['lock','keep'],default='keep',help='In track mode: auto-focus while stationary, then lock after one second of valid tag detection')
        q.add_argument('--focus',type=int,help='Explicit fixed C920 focus control, 0..250; overrides focus-mode')
    q = sub.add_parser('print'); tag(q); board(q)
    q.add_argument('--output',default='apriltag_prints'); q.set_defaults(func=prints)
    q = sub.add_parser('calibrate'); board(q); cam(q)
    q.add_argument('--images',help='Calibrate from a directory of photographs instead of a live camera')
    q.add_argument('--output',required=True); q.set_defaults(func=calibrate)
    q = sub.add_parser('inspect'); cam(q); q.set_defaults(func=inspect_camera)
    q = sub.add_parser('track'); tag(q); cam(q)
    q.add_argument('--forward-axis',choices=['x','y','-x','-y'],default='y',help='Tag axis aligned with rover forward')
    q.add_argument('--calibration',required=True)
    q.add_argument('--output',required=True)
    q.add_argument('--time-offset-s',type=float,required=True,help='Measured ROS sensor epoch minus camera receipt epoch, including capture latency')
    q.add_argument('--duration',type=float,default=0,help='Seconds; 0 until Ctrl+C or q')
    q.add_argument('--max-reprojection-px',type=float,default=2)
    q.add_argument('--free-motion',action='store_true',help='Record full pose without straight-run rotation/lateral gate; GT only')
    q.add_argument('--max-rotation-deg',type=float,default=10)
    q.add_argument('--max-lateral-m',type=float,default=.1)
    q.add_argument('--nominal-speed',type=float,default=.05,help='Metadata only, never a motion command')
    q.add_argument('--no-preview',action='store_true')
    q.set_defaults(func=track,focus_mode="lock")
    a = p.parse_args()
    if getattr(a,'square_size_mm',None) is not None:
        a.square_size = a.square_size_mm/1000.
    for name in ('tag_size','square_size','fps','max_reprojection_px','max_rotation_deg','max_lateral_m'):
        if hasattr(a,name) and (not np.isfinite(getattr(a,name)) or getattr(a,name)<=0):
            p.error(name+' must be finite and positive')
    if hasattr(a,'tag_id') and not 0<=a.tag_id<587:
        p.error('tag-id must be 0..586')
    if hasattr(a,'time_offset_s') and not np.isfinite(a.time_offset_s):
        p.error('time offset must be finite')
    for name in ('width','height','cols','rows'):
        if hasattr(a,name) and getattr(a,name)<=0:
            p.error(name+' must be positive')
    if hasattr(a,'duration') and (not np.isfinite(a.duration) or a.duration<0):
        p.error('duration must be finite and nonnegative')
    if hasattr(a,'focus') and a.focus is not None and not 0<=a.focus<=250:
        p.error('focus must be 0..250')
    a.func(a)


if __name__ == '__main__':
    main()
