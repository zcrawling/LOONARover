"""Evaluate C experiment against existing time-aligned AprilTag comparison CSV.
GT input is exclusively evaluation data; all timestamps must already be ROS epoch.
"""
import argparse,csv,json
from pathlib import Path
import numpy as np


def bracket_sample(t, data, columns, max_gap):
    i=np.searchsorted(data[:,0],t)
    if i<len(data) and abs(data[i,0]-t)<1e-7:return data[i,columns]
    if i==0 or i==len(data) or data[i,0]-data[i-1,0]>max_gap:return None
    w=(t-data[i-1,0])/(data[i,0]-data[i-1,0])
    return data[i-1,columns]*(1-w)+data[i,columns]*w


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--samples',type=Path,required=True)
    p.add_argument('--gt-comparison',type=Path,required=True,help='compare_primitive_test.py comparison.csv with ROS-aligned GT')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    samples=list(csv.DictReader(a.samples.open()));grows=list(csv.DictReader(a.gt_comparison.open()))
    # Consume one copy of GT; the baseline comparison contains repeated GT per topic.
    gt=np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y','gt_yaw']] for r in grows if r['topic']=='/localization/dr'])
    test=np.array([[float(r[k]) for k in ['t','x','y','yaw','vx_encoder']] for r in samples])
    if len(gt)<2 or len(test)<2 or np.any(np.diff(gt[:,0])<=0) or np.any(np.diff(test[:,0])<=0):raise ValueError('Missing/nonmonotonic input')
    # Begin both trajectories at the first common observed GT pose. No scale fitting.
    start=max(gt[0,0],test[0,0]);gt=gt[gt[:,0]>=start];origin=bracket_sample(gt[0,0],test,[1,2,3],.08)
    if origin is None:raise ValueError('No common valid start')
    angle=gt[0,3]-origin[2];R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    errors=[];paired=[]
    for g in gt:
        x=bracket_sample(g[0],test,[1,2,3],.08)
        if x is None:continue
        xy=R@(x[:2]-origin[:2])+gt[0,1:3];err=float(np.linalg.norm(xy-g[1:3]));errors.append(err);paired.append(dict(t=float(g[0]),test_x=float(xy[0]),test_y=float(xy[1]),gt_x=float(g[1]),gt_y=float(g[2]),position_error_m=err))
    segments=[];begin=0
    for end in range(1,len(samples)+1):
        if end<len(samples) and samples[end]['phase']==samples[begin]['phase']:continue
        phase=samples[begin]['phase'];d=test[begin:end]
        if phase!='STOP' and len(d)>2:
            g0=bracket_sample(d[0,0],gt,[1,2,3],.25);g1=bracket_sample(d[-1,0],gt,[1,2,3],.25)
            ds=float(np.sum(np.diff(d[:,0])*(d[1:,4]+d[:-1,4])*.5));cgt=None
            if g0 is not None and g1 is not None and abs(ds)>.01 and max(np.diff(d[:,0]))<=.08:
                actual=float((g1[:2]-g0[:2])@np.array([np.cos(g0[2]),np.sin(g0[2])]))
                cgt=actual/ds
            segments.append(dict(phase=phase,start=float(d[0,0]),end=float(d[-1,0]),encoder_distance=ds,C_GT=cgt))
        begin=end
    baselines={}
    for topic in sorted({r['topic'] for r in grows}):
        # Re-align each baseline at exactly the test/GT common origin.
        source=[r for r in grows if r['topic']==topic]
        baseline=np.array([[float(r[k]) for k in ['t_ros','odom_x','odom_y','odom_yaw']] for r in source])
        b0=bracket_sample(gt[0,0],baseline,[1,2,3],.08)
        if b0 is None:continue
        theta=gt[0,3]-b0[2];rot=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
        values=[]
        for pair in paired:
            b=bracket_sample(pair['t'],baseline,[1,2,3],.08)
            if b is None:continue
            xy=rot@(b[:2]-b0[:2])+gt[0,1:3]
            values.append(float(np.linalg.norm(xy-[pair['gt_x'],pair['gt_y']])))
        if values:baselines[topic]=dict(samples=len(values),rmse_m=float(np.sqrt(np.mean(np.square(values)))),last_m=values[-1])
    if not errors:raise ValueError('No paired observations')
    last=samples[-1];result=dict(C_acc=last['C_acc'],C_dec=last['C_dec'],C_valid=last['C_valid'],segments=segments,
        odom_c_test=dict(samples=len(errors),rmse_m=float(np.sqrt(np.mean(np.square(errors)))),last_m=errors[-1]),baselines=baselines,
        caveats=['GT already ROS-clock aligned; no time offset fitted here.', 'C_GT is signed endpoint projection for straight motion.',
                 'All trajectories start-aligned at the first common GT time; missing baseline pairs are counted separately.',
                 'C_dec is retrospective at confirmed STOP; online pose is not rewritten.'])
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'evaluation.json').write_text(json.dumps(result,indent=2))
    with (a.output/'paired.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
