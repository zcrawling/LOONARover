"""Audit existing trials only; no ROS publishers or sensor access."""
from pathlib import Path
import csv,json
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'data/apriltag_gt/sand_analysis_20260917';out.mkdir(exist_ok=True)
results=[]
for p in sorted((ROOT/'data/apriltag_gt').glob('c_vision_20260917*')):
 meta=json.loads((p/'test.json').read_text())
 if not (p/'comparison.csv').exists():
  results.append(dict(trial=p.name,status=meta['status'],excluded='no comparison/bag'));continue
 s=list(csv.DictReader((p/'rover/estimate/samples.csv').open()))
 t=np.array([float(r['t']) for r in s]);v=np.array([float(r['vx_encoder']) for r in s]);phase=np.array([r['phase'] for r in s])
 start=t[np.flatnonzero(phase=='ACCEL')[0]];end=t[np.flatnonzero(phase=='DECEL')[-1]]
 g=[r for r in csv.DictReader((p/'comparison.csv').open()) if r['topic']=='/localization/dr']
 gt=np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y','gt_yaw','odom_x','odom_y']] for r in g])
 pre=gt[(gt[:,0]>start-1)&(gt[:,0]<start-.1)];post=gt[(gt[:,0]>end+1)&(gt[:,0]<end+2.5)]
 camera=list(csv.DictReader((p/'camera/frames.csv').open()))
 r=dict(trial=p.name,status=meta['status'],tof=meta.get('tof'),profile=meta['profile'],camera_valid_fraction=sum(x['valid']=='1' for x in camera)/len(camera),max_paired_GT_gap_s=float(np.diff(gt[:,0]).max()),pre_samples=len(pre),post_samples=len(post))
 if len(pre)>=5 and len(post)>=5:
  a=np.median(pre,axis=0);b=np.median(post,axis=0)
  # Integrate vx between representative times; STOP endpoints reduce latency sensitivity.
  tt=np.r_[a[0],t[(t>a[0])&(t<b[0])],b[0]];vv=np.interp(tt,t,v)
  ds=float(np.sum(np.diff(tt)*(vv[1:]+vv[:-1])/2))
  r.update(encoder_m=ds,GT_forward_m=float(b[1]-a[1]),GT_lateral_m=float(b[2]-a[2]),C_GT=float((b[1]-a[1])/ds),GT_pre_scatter_mm=float(np.std(pre[:,1])*1000),GT_post_scatter_mm=float(np.std(post[:,1])*1000))
 # Non-overlapping 1 s windows; endpoint interpolation only across <=0.15 s gaps.
 local=[]
 for ta in np.arange(start,end-1,1.):
  tb=ta+1
  ia=np.searchsorted(gt[:,0],ta);ib=np.searchsorted(gt[:,0],tb)
  if ia<1 or ib>=len(gt) or gt[ia,0]-gt[ia-1,0]>.15 or gt[ib,0]-gt[ib-1,0]>.15:continue
  tt=np.r_[ta,t[(t>ta)&(t<tb)],tb];vv=np.interp(tt,t,v)
  ds=float(np.sum(np.diff(tt)*(vv[1:]+vv[:-1])/2))
  if ds<.05:continue
  dx=float(np.interp(tb,gt[:,0],gt[:,1])-np.interp(ta,gt[:,0],gt[:,1]))
  local.append(dict(start=float(ta),C=dx/ds,encoder_m=ds,GT_forward_m=dx))
 r['one_second_windows']=local
 r['windows']=json.loads((p/'c_comparison.json').read_text())
 r['errors']=json.loads((p/'evaluation/evaluation.json').read_text())
 r['C_applied_fraction']=sum(abs(float(x['C_applied'])-1)>1e-6 for x in s)/len(s)
 r['phases']={}
 for ph in ['STOP','ACCEL','CRUISE','DECEL']:
  rows=[x for x in s if x['phase']==ph and x['bias_ready']=='True'];aa=np.array([float(x['a_corrected']) for x in rows])
  bias=np.array([float(x['accel_bias']) for x in rows])
  r['phases'][ph]=dict(n=len(rows),a_median=float(np.median(aa)),a_min=float(aa.min()),a_max=float(aa.max()),bias_min=float(bias.min()),bias_max=float(bias.max())) if len(aa) else {}
 results.append(r)
(out/'summary.json').write_text(json.dumps(results,indent=2))
for r in results:
 print(r['trial'], {k:v for k,v in r.items() if k not in ['trial','windows','errors','phases','profile','one_second_windows']})
 if 'phases' in r: print('acceleration:',r['phases'])
