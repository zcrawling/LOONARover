"""Offline interval labels; never publishes robot commands."""
import csv
import json
import math
import subprocess
import time
from pathlib import Path
import numpy as np


def clock_probe(ssh, count=5):
    samples=[]
    for _ in range(count):
        before=time.time(); mono=time.monotonic()
        result=subprocess.run(ssh+['python3 -c "import time; print(time.time())"'],capture_output=True,text=True,timeout=8)
        after=time.time();elapsed=time.monotonic()-mono
        if result.returncode==0 and abs(after-before-elapsed)<.02:
            remote=float(result.stdout.strip())
            samples.append(dict(offset_s=remote-(before+after)/2,rtt_s=elapsed,local_epoch=(before+after)/2))
    if not samples:raise RuntimeError('No valid clock samples')
    return dict(best=min(samples,key=lambda x:x['rtt_s']),samples=samples,definition='rover epoch minus laptop epoch; RTT/2 is an uncertainty bound, not camera exposure calibration')


def motion_intervals(events,settle,guard=.2):
    intervals=[];start=None;last=None
    for e in events:
        t=e['ros_stamp_ns']/1e9
        moving=e['event']=='motion' and e['linear_mps']>0
        if start is not None and (not moving or (last is not None and t-last>.2)):
            end=t if not moving else last
            if end-guard>start+settle:intervals.append((start+settle,end-guard))
            start=None
        if moving and start is None:start=t
        last=t
    # An unfinished final motion segment is deliberately not labelled.
    return intervals


def analyze(out,settle=2.,lengths=(3.,5.)):
    out=Path(out);state=json.loads((out/'test.json').read_text())
    offset=state['clock_before']['best']['offset_s']
    events=[json.loads(x) for x in (out/'rover/command-events.jsonl').read_text().splitlines()]
    intervals=motion_intervals(events,settle)
    with (out/'rover/wheel-samples.csv').open() as f:w=np.array([[float(x[k]) for k in ('t','vx','wz')] for x in csv.DictReader(f)])
    with (out/'camera/frames.csv').open() as f:frames=list(csv.DictReader(f))
    good=[x for x in frames if x['valid']=='1' and x['s_m']]
    gt=np.array([[float(x['t'])+offset,float(x['s_m']),float(x['reprojection_px'])] for x in good])
    if len(w)<2 or len(gt)<2:raise ValueError('Insufficient paired samples')
    if np.any(np.diff(w[:,0])<=0) or np.any(np.diff(gt[:,0])<=0):raise ValueError('Nonmonotonic timestamps')
    wd=np.r_[0,np.cumsum(np.diff(w[:,0])*(w[1:,1]+w[:-1,1])/2)]
    rows=[]
    for segment,(start,end) in enumerate(intervals):
        for length in lengths:
            for a in np.arange(start,end-length+1e-7,length):
                b=a+length;g=gt[(gt[:,0]>=a)&(gt[:,0]<=b)]
                total=sum(a<=float(x['t'])+offset<=b for x in frames)
                reason='ok';gap=None
                if len(g)<8:reason='too_few_tag_samples'
                else:
                    gap=float(max(np.diff(np.r_[a,g[:,0],b])))
                    if gap>.2:reason='tag_gap'
                wi=w[(w[:,0]>=a)&(w[:,0]<=b)]
                if len(wi)<2 or max(np.diff(np.r_[a,wi[:,0],b]))>.1:reason='wheel_gap'
                row=dict(segment=segment,start_ros=a,end_ros=b,window_s=length,status=reason,tag_samples=len(g),observed_fraction=len(g)/total if total else 0,max_tag_gap_s=gap)
                if reason=='ok':
                    t=g[:,0]-g[:,0].mean();z=g[:,1];camera_slope=float(t@(z-z.mean())/(t@t))
                    enc=np.interp(g[:,0],w[:,0],wd);encoder_slope=float(t@(enc-enc.mean())/(t@t))
                    row.update(camera_delta_m=camera_slope*length,wheel_delta_m=encoder_slope*length,fit_residual_rms_m=float(np.sqrt(np.mean((z-z.mean()-camera_slope*t)**2))),reprojection_mean_px=float(g[:,2].mean()),wheel_vx_std=float(wi[:,1].std()))
                    if encoder_slope*length<.05:row['status']='insufficient_wheel_distance'
                    else:row['C']=camera_slope/encoder_slope
                rows.append(row)
    fields=list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    with (out/'c_windows.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    summary=dict(settle_seconds=settle,stop_guard_seconds=.2,window_seconds=lengths,intervals=intervals,windows=len(rows),accepted=sum(r['status']=='ok' for r in rows),clock_offset_s=offset,clock_rtt_s=state['clock_before']['best']['rtt_s'],training_verified=False,note='C uses camera and encoder fitted slopes at identical camera timestamps. Separate 3s/5s datasets overlap: never pool as independent samples. Residuals describe both real speed changes and measurement noise. Camera exposure delay and focus scale remain uncalibrated.')
    if 'clock_after' in state:summary['clock_offset_change_s']=state['clock_after']['best']['offset_s']-offset
    (out/'c_analysis.json').write_text(json.dumps(summary,indent=2))
    return summary
