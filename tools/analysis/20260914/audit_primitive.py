"""Per-primitive, STOP and GT-coverage audit of an existing completed trial."""
import csv,json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=Path(sys.argv[1]);events=[json.loads(x) for x in (p/'rover/events.jsonl').read_text().splitlines()];states=[json.loads(x) for x in (p/'rover/states.jsonl').read_text().splitlines()]
rows=list(csv.DictReader((p/'comparison.csv').open()));topics=sorted(set(r['topic'] for r in rows));arrays={name:np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y','gt_yaw','odom_x','odom_y','odom_yaw']] for r in rows if r['topic']==name]) for name in topics};gt=arrays['/localization/dr'][:,:4];t0=events[0]['t'];st=np.array([r['t'] for r in states]);trans=[r for r in events if r['kind']=='transition'];moves=[r for r in trans if r['intent']['reason']=='running'];commands=[r for r in events if r['kind']!='transition'];ct=np.array([r['t'] for r in commands]);cv=np.array([[r['vx'],r['wz']] for r in commands]);indices=np.clip(np.searchsorted(ct,st,side='right')-1,0,len(ct)-1);nonzero=np.any(abs(cv[indices])>1e-8,axis=1);zero=np.array([r['zero_update'] for r in states]);v=np.array([r['encoder_vx'] for r in states])

def snapshot(a,start,end):
 m=(a[:,0]>=start)&(a[:,0]<=end)
 if m.sum()<3:return None
 x=a[m]
 # Use the longest actually observed contiguous cluster; never fill GT gaps.
 cuts=np.r_[0,np.flatnonzero(np.diff(x[:,0])>.25)+1,len(x)]
 chunks=[x[a:b] for a,b in zip(cuts[:-1],cuts[1:]) if b-a>=3]
 if not chunks:return None
 return np.median(max(chunks,key=len)[:,1:],axis=0)

result=[]
for i,move in enumerate(moves):
 start=move['t'];stop=next(r['t'] for r in trans if r['t']>start and r['intent']['reason']=='motion_target_reached');next_start=moves[i+1]['t'] if i+1<len(moves) else events[-1]['t']
 before=(start-1.,start-.1);after=(next_start-1.,next_start-.1)
 g0=snapshot(gt,*before);g1=snapshot(gt,*after);is_turn=move['intent']['primitive']=='ROTATE_LEFT';stage=move['stage'];target=([0,30,60,60,30][stage] if is_turn else [.5,.5,.2,.3,.5][stage])
 r=dict(index=i+1,kind='turn' if is_turn else 'straight',target=target,command_seconds=stop-start,stop_seconds=next_start-stop,start_elapsed=start-t0,stop_elapsed=stop-t0)
 mask=(st>=stop)&(st<next_start);found=np.flatnonzero(mask&zero);r['stationary_delay_s']=float(st[found[0]]-stop) if len(found) else None
 if len(found):
  first=found[0];last=found[-1];pose=np.array([states[k]['pose'] for k in [first,last]]);r['zupt_pose_drift_m']=float(np.linalg.norm(pose[1,:2]-pose[0,:2]));r['zupt_yaw_drift_deg']=float(np.degrees(pose[1,2]-pose[0,2]))
 if g0 is not None and g1 is not None:
  r['gt_displacement_m']=float(np.linalg.norm(g1[:2]-g0[:2]));r['gt_yaw_change_deg']=float(np.degrees(g1[2]-g0[2]));r['gt_forward_projection_m']=float((g1[:2]-g0[:2])@np.array([np.cos(g0[2]),np.sin(g0[2])]))
  for name,a in arrays.items():
   x0=snapshot(a,*before);x1=snapshot(a,*after)
   if x0 is None or x1 is None:continue
   r[name]=dict(displacement_m=float(np.linalg.norm(x1[3:5]-x0[3:5])),yaw_change_deg=float(np.degrees(x1[5]-x0[5])))
 result.append(r)
valid=gt[:,0];dt=np.diff(valid);within=(valid[-1]-valid[0]);temporal_coverage=1-float(np.sum(dt[dt>.25])/within)
summary=dict(motions=result,command_curve_samples=int(np.sum(np.all(abs(cv)>1e-8,axis=1))),zero_update_samples=int(zero.sum()),zero_during_nonzero_command_samples=int(np.sum(zero&nonzero)),max_encoder_speed_while_zero=float(np.max(abs(v[zero]))),bias_start_degps=float(np.degrees(states[0]['bias'][2])),bias_final_degps=float(np.degrees(states[-1]['bias'][2])),gt_max_gap_s=float(max(dt)),gt_gaps_over_250ms=int(sum(dt>.25)),approx_gt_temporal_coverage=temporal_coverage,gt_total_yaw_deg=float(np.degrees(gt[-1,3]-gt[0,3])))
(p/'primitive_audit.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
fig,axs=plt.subplots(2,1,figsize=(11,7),layout='constrained')
for ax,kind,key in [(axs[0],'straight','gt_forward_projection_m'),(axs[1],'turn','gt_yaw_change_deg')]:
 sub=[r for r in result if r['kind']==kind and key in r];x=np.arange(len(sub));ax.bar(x-.18,[r['target'] for r in sub],.35,label='Requested');ax.bar(x+.18,[r[key] for r in sub],.35,label='GT stop-to-stop');ax.set_xticks(x,[str(r['index']) for r in sub]);ax.legend();ax.grid(axis='y',alpha=.2);ax.set_ylabel('Distance (m)' if kind=='straight' else 'Left turn (deg)');ax.set_xlabel('Primitive number')
fig.savefig(p/'primitive_segments.png',dpi=130);plt.close(fig)
