"""Offline stone trial C audit. Fixed settings, GT never used for fitting."""
import csv,json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from rosbags.highlevel import AnyReader
from rosbags.typesys import get_typestore,Stores
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'data/apriltag_gt/stone_c_reanalysis';OUT.mkdir(exist_ok=True)
def integ(t,a):return np.r_[0,np.cumsum(np.diff(t)*(a[1:]+a[:-1])*.5)]
def fit_c(t,v,a):
 vi=integ(t,a);ok=abs(v)>=.02
 return dict(C_ls=float(v[ok]@vi[ok]/(v[ok]@v[ok])),C_distance=float(integ(t,vi)[-1]/integ(t,v)[-1]))
def shortfit(t,v,a,lo,hi,width):
 rows=[];y=[]
 for left in np.arange(lo,hi-width+1e-6,width):
  right=left+width;tt=np.r_[left,t[(t>left)&(t<right)],right]
  if max(np.diff(tt))>.08:continue
  rows.append([np.interp(right,t,v)-np.interp(left,t,v),width]);y.append(integ(tt,np.interp(tt,t,a))[-1])
 X=np.array(rows);y=np.array(y);sc=np.linalg.norm(X,axis=0)
 cond=float(np.linalg.cond(X/sc))
 initial=np.linalg.lstsq(X,y,rcond=None)[0]
 sol=least_squares(lambda beta:X@beta-y,initial,loss='huber',f_scale=.02*width).x
 return dict(C=float(sol[0]),bias_mps2=float(sol[1]),condition=cond,n=len(y),velocity_increment_residual_rms=float(np.sqrt(np.mean((X@sol-y)**2))))
def main():
 results=[];fig,axes=plt.subplots(4,2,figsize=(12,13),layout='constrained')
 for idx,p in enumerate(sorted((ROOT/'data/apriltag_gt').glob('c_vision_험지_돌바닥*'))):
  samples=list(csv.DictReader((p/'rover/estimate/samples.csv').open()));st=np.array([float(r['t']) for r in samples]);sv=np.array([float(r['vx_encoder']) for r in samples]);ph=np.array([r['phase'] for r in samples])
  windows=[json.loads(x) for x in (p/'rover/estimate/windows.jsonl').read_text().splitlines()];acc=next(w for w in windows if w['kind']=='acceleration');dec=next(w for w in windows if w['kind']=='deceleration')
  lo=acc['rows'][0]['t'];end=dec['rows'][-1]['t'];rows=[];tf_ok=False
  with AnyReader([p/'rover/bag'],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
   for c,_,raw in bag.messages(connections=[c for c in bag.connections if c.topic in ['/imu','/tf_static']]):
    m=bag.deserialize(raw,c.msgtype)
    if c.topic=='/tf_static':
     for tr in m.transforms:
      if tr.header.frame_id=='base_link' and tr.child_frame_id=='imu_link':
       q=tr.transform.rotation;tf_ok=np.allclose([q.x,q.y,q.z,q.w],[0,0,0,1])
     continue
    assert m.header.frame_id=='imu_link'
    rows.append([m.header.stamp.sec+m.header.stamp.nanosec/1e9,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
  assert tf_ok,'Unexpected extrinsic; implement transform before analysis'
  d=np.array(rows);d=d[(d[:,0]>=lo-1.2)&(d[:,0]<=end+.1)];t=d[:,0];assert (np.diff(t)>0).all() and max(np.diff(t))<.08
  stat=(t>=lo-1.1)&(t<=lo-.1);assert stat.sum()>20
  assert np.max(abs(np.interp(t[stat],st,sv)))<.005
  a0=np.mean(d[stat,1:4],axis=0);gb=np.mean(d[stat,4:7],axis=0)
  # Initial gravity direction assumed parallel to stationary acceleration; bias not independently identifiable.
  g=a0.copy();gs=[]
  for j in range(len(t)):
   if j:g=Rotation.from_rotvec(-(.5*(d[j-1,4:7]+d[j,4:7])-gb)*(t[j]-t[j-1])).apply(g)
   gs.append(g.copy())
  gs=np.array(gs);dynamic=d[:,1]-gs[:,0]
  # Re-zero only using same pre-motion reference, never GT or post-motion data.
  dynamic-=np.mean(dynamic[stat]);raw=d[:,1]-a0[0]
  ar=acc['rows'];at=np.array([x['t'] for x in ar]);av=np.array([x['vx_encoder'] for x in ar]);aa=np.array([x['a_corrected'] for x in ar])
  estimates={'archived_static':fit_c(at,av,aa),'gyro_gravity_proxy':fit_c(at,av,np.interp(at,t,dynamic))}
  # Full-profile estimates are offline/retrospective; local integral windows do not accumulate drift across run.
  aa_dyn=np.interp(st,t,dynamic);aa_static=np.interp(st,t,raw)
  for w in [.3,.5,.75]:
   for label,signal in [('static',aa_static),('gyro',aa_dyn)]:estimates[f'short_{label}_{w}']=shortfit(st,sv,signal,lo,end,w)
  # Both end velocities zero: retrospective constant residual bias removal.
  bt=np.r_[lo,st[(st>lo)&(st<end)],end];bv=np.interp(bt,st,sv)
  for label,signal in [('static',aa_static),('gyro',aa_dyn)]:
   ba=np.interp(bt,st,signal);vi=integ(bt,ba);bias=vi[-1]/(bt[-1]-bt[0]);closed=vi-bias*(bt-bt[0]);mask=abs(bv)>=.02
   estimates['stop_closure_'+label]=dict(C=float(bv[mask]@closed[mask]/(bv[mask]@bv[mask])),residual_bias_mps2=float(bias),uncorrected_end_velocity=float(vi[-1]))
  # Acceleration-only joint fit diagnostic shows C/bias conditioning under near-constant ramp.
  estimates['accel_only_joint']=shortfit(st,sv,aa_dyn,lo,at[-1],.5)
  cm=json.loads((p/'c_comparison.json').read_text());gt_acc=next(x for x in cm['windows'] if x['window']=='acceleration')['C_GT']
  comp=[r for r in csv.DictReader((p/'comparison.csv').open()) if r['topic']=='/localization/dr'];gt=np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y']] for r in comp])
  def endpoint(x):
   k=np.searchsorted(gt[:,0],x)
   if k<1 or k>=len(gt) or gt[k,0]-gt[k-1,0]>.25:return None
   return float(np.interp(x,gt[:,0],gt[:,1]))
  ga,ge=endpoint(lo),endpoint(end);tt=np.r_[lo,st[(st>lo)&(st<end)],end];se=integ(tt,np.interp(tt,st,sv))[-1]
  cgt=None if ga is None or ge is None else (ge-ga)/se
  result=dict(trial=p.name,C_GT_acceleration=gt_acc,C_GT_full_profile=cgt,estimates=estimates,initial_acceleration=a0.tolist(),gyro_bias=gb.tolist(),gyro_pitch_excursion_deg=float(np.ptp(np.arctan2(gs[:,0],gs[:,2]))*180/np.pi),notes='Gyro gravity is conditional: stationary acceleration used as gravity vector, constant sensor bias not separately calibrated. Full-profile C assumes one C across accel/cruise/decel. No GT fit. Current online validity unchanged.')
  results.append(result)
  ax=axes[idx,0];time=t-lo;ax.plot(time,raw,label='Static offset only',alpha=.6);ax.plot(time,dynamic,label='Gyro gravity proxy',alpha=.8);ax.set(xlim=(-1,end-lo+.1),ylabel='Forward acceleration (m/s²)',title=p.name.replace('c_vision_험지_','').replace('돌바닥','Stone'));ax.axhline(0,color='grey',lw=.8)
  ax=axes[idx,1];ok=(gt[:,0]>=lo)&(gt[:,0]<=end);gplot=gt[ok].copy();mask=np.r_[False,np.diff(gplot[:,0])>.25];gplot[mask,1]=np.nan
  if ga is not None:ax.plot(gplot[:,0]-lo,gplot[:,1]-ga,label='AprilTag observed X')
  vv=np.interp(tt,st,sv);ss=integ(tt,vv);ax.plot(tt-lo,ss,label='Encoder')
  ax.plot(tt-lo,ss*estimates['short_gyro_0.5']['C'],label='Offline C × encoder',linestyle='--');ax.set(xlabel='Time from acceleration start (s)',ylabel='Displacement (m)')
 for ax in axes.ravel():ax.grid(alpha=.2);ax.legend(fontsize=8)
 fig.savefig(OUT/'comparison.png',dpi=140);plt.close(fig)
 (OUT/'results.json').write_text(json.dumps(results,indent=2))
 for r in results:
  print(r['trial'],'GTacc/full',r['C_GT_acceleration'],r['C_GT_full_profile'],'pitch excursion',round(r['gyro_pitch_excursion_deg'],2))
  for k,v in r['estimates'].items():print(' ',k,{kk:round(vv,4) for kk,vv in v.items()})

if __name__=='__main__':main()
