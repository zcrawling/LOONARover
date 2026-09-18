"""September 10 C/IMU audit. Offline only; no label-dependent window selection."""
from pathlib import Path
import sys,json,csv,importlib.util
from collections import Counter
from itertools import permutations
import numpy as np
from scipy.stats import spearmanr,pearsonr,rankdata
from rosbags.highlevel import AnyReader
from rosbags.typesys import get_typestore,Stores
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'data/apriltag_gt/analysis_20260910';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'tools/apriltag_gt'))
from loonar_apriltag.trial_analysis import motion_intervals
spec=importlib.util.spec_from_file_location('previous',ROOT/'tools/analysis/20260909/correlate_quality.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
CONFIG=dict(window_s=3,settle_s=2,stop_guard_s=.5,scan_stride_s=.5,strict=dict(fraction=.95,gap=.25,rms=.003,reprojection=1.,heading_range=3.),screened=dict(fraction=.9,gap=.4,rms=.005,reprojection=1.5,heading_range=5.),shift_s=[-.1,0,.1],C_shift_range_max=.04)

def readcsv(p):
 with p.open() as f:return list(csv.DictReader(f))
def sl(t,x):return old.slope(t,x)
def rho(x,y):return float(spearmanr(x,y).statistic) if np.ptp(x)>1e-12 and np.ptp(y)>1e-12 else 0.
def extract():
 audits=[];candidates=[]
 for p in sorted((ROOT/'data/apriltag_gt').rglob('tag_20260910*')):
  if not p.is_dir():continue
  note=dict(run=p.name,path=str(p.relative_to(ROOT)));audits.append(note)
  paths=list(p.glob('**/bag/metadata.yaml'))
  if not paths or not (p/'camera/frames.csv').exists():note['status']='missing_bag_or_camera';continue
  state=json.loads((p/'test.json').read_text());meta=json.loads((p/'camera/capture.json').read_text());note.update(speed=state.get('speed_mps'),run_status=state.get('status'),focus=meta.get('focus_lock'))
  if 'clock_before' not in state:note['status']='no_measured_clock_offset';continue
  before=state['clock_before']['best'];after=state.get('clock_after',{}).get('best',before)
  note.update(offset_change=after['offset_s']-before['offset_s'],rtt=before['rtt_s'])
  if meta.get('forward_axis')!='x':note['status']='unverified_axis';continue
  def clock(t):return t+np.interp(t,[before['local_epoch'],after['local_epoch']],[before['offset_s'],after['offset_s']])
  events=paths[0].parent.parent/'command-events.jsonl'
  if not events.exists():note['status']='no_motion_events';continue
  intervals=motion_intervals([json.loads(l) for l in events.read_text().splitlines()],2,.5);note['steady_intervals']=intervals
  im=[];wheel=[];joint=[]
  with AnyReader([paths[0].parent],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
   for conn,bt,data in bag.messages(connections=[c for c in bag.connections if c.topic in ['/imu','/wheel/odom','/wheel/odometer']]):
    m=bag.deserialize(data,conn.msgtype);t=m.header.stamp.sec+m.header.stamp.nanosec/1e9
    if conn.topic=='/imu':im.append([t,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
    elif conn.topic=='/wheel/odom':wheel.append([t,m.twist.twist.linear.x,m.twist.twist.angular.z])
    elif len(m.position)>=2:joint.append([t,*m.position[:2]])
  im=np.array(im);w=np.array(wheel);jj=np.array(joint)
  if len(im)<2 or len(w)<2:note['status']='missing_sensors';continue
  if any(np.any(np.diff(x[:,0])<=0) for x in [im,w]):note['status']='nonmonotonic_sensor_time';continue
  frames=readcsv(p/'camera/frames.csv');all_t=np.array([float(r['t']) for r in frames]);ft=clock(all_t)
  good=[r for r in frames if r['valid']=='1' and r['s_m']]
  if len(good)<2:note['status']='no_valid_tag';continue
  g=np.array([[float(r[k]) for k in ['t','s_m','reprojection_px','heading_change_deg']] for r in good]);rawt=g[:,0].copy();g[:,0]=clock(rawt)
  if np.any(np.diff(g[:,0])<=0):note['status']='nonmonotonic_camera_time';continue
  wd=np.r_[0,np.cumsum(np.diff(w[:,0])*(w[1:,1]+w[:-1,1])/2)]
  note.update(status='reviewed',imu_hz=1/np.median(np.diff(im[:,0])),wheel_hz=1/np.median(np.diff(w[:,0])),camera_hz=1/np.median(np.diff(ft)))
  for seg,(left,right) in enumerate(intervals):
   for a in np.arange(left,right-3+1e-7,.5):
    b=a+3;gg=g[(g[:,0]>=a)&(g[:,0]<=b)];ii=im[(im[:,0]>=a)&(im[:,0]<=b)];ww=w[(w[:,0]>=a)&(w[:,0]<=b)]
    row=dict(run=p.name,segment=seg,start=a,end=b,speed=note['speed'],clock_change=note['offset_change'])
    candidates.append(row)
    if len(gg)<12 or len(ii)<270 or len(ww)<120:row['reason']='sample_count';continue
    if np.max(np.diff(np.r_[a,ii[:,0],b]))>.04 or np.max(np.diff(np.r_[a,ww[:,0],b]))>.08:row['reason']='sensor_gap';continue
    gap=np.max(np.diff(np.r_[a,gg[:,0],b]));frac=len(gg)/max(1,np.sum((ft>=a)&(ft<=b)))
    cam=sl(gg[:,0],gg[:,1]);res=np.sqrt(np.mean((gg[:,1]-gg[:,1].mean()-cam*(gg[:,0]-gg[:,0].mean()))**2))
    cs=[]
    for shift in [-.1,0,.1]:
     t=gg[:,0]+shift
     cs.append(cam/sl(t,np.interp(t,w[:,0],wd)))
    row.update(C=cs[1],C_minus=cs[0],C_plus=cs[2],rms=float(res),gap=float(gap),fraction=frac,reprojection=float(gg[:,2].max()),heading_range=float(np.ptp(gg[:,3])),tag_n=len(gg))
    if not np.isfinite(cs).all() or np.ptp(cs)>.04:row['reason']='time_shift_sensitive';continue
    if ww[:,1].mean()<.02:row['reason']='insufficient_motion';continue
    row['reason']='quality';row['strict']=False;row['screened']=False;row['rejections']={}
    for tier in ['strict','screened']:
     q=CONFIG[tier];row['rejections'][tier]=[n for n,ok in [('tag_fraction',frac>=q['fraction']),('tag_gap',gap<=q['gap']),('fit_rms',res<=q['rms']),('reprojection',gg[:,2].max()<=q['reprojection']),('heading_range',np.ptp(gg[:,3])<=q['heading_range']),('clock_change',abs(note['offset_change'])<=.1)] if not ok];row[tier]=bool(frac>=q['fraction'] and gap<=q['gap'] and res<=q['rms'] and gg[:,2].max()<=q['reprojection'] and np.ptp(gg[:,3])<=q['heading_range'] and abs(note['offset_change'])<=.1)
    if row['strict'] or row['screened']:
     # Fixed 100 Hz grid strictly inside the window; no endpoint extrapolation.
     ts=np.arange(300)/100+a;interp=np.column_stack([ts,*[np.interp(ts,im[:,0],im[:,k]) for k in range(1,7)]])
     row['features']=old.features(interp,ww)
     # Norm features remove some mounting-orientation sensitivity.
     for name,x in [('acc_norm',np.linalg.norm(interp[:,1:4],axis=1)),('gyro_norm',np.linalg.norm(interp[:,4:7],axis=1))]:
      row['features'][name+'_std']=float(x.std());row['features'][name+'_diff_rms']=float(np.sqrt(np.mean(np.diff(x)**2)))
     if len(jj)>0:
      z=jj[(jj[:,0]>=a)&(jj[:,0]<=b)]
      if len(z)>2:
       rates=np.diff(z[:,1:],axis=0)/np.diff(z[:,0])[:,None]
       for name,x in [('wheel_left',rates[:,0]),('wheel_right',rates[:,1]),('wheel_difference',rates[:,0]-rates[:,1])]:
        row['features'][name+'_mean']=float(x.mean());row['features'][name+'_std']=float(x.std())
  print(p.name,note['status'],sum(r.get('strict',False) for r in candidates if r['run']==p.name),sum(r.get('screened',False) for r in candidates if r['run']==p.name),flush=True)
 return audits,candidates

def select(candidates,tier):
 out=[];ends={}
 for r in candidates:
  if r.get(tier) and r['start']>=ends.get(r['run'],-np.inf):out.append(r);ends[r['run']]=r['end']
 return out

def correlations(rows):
 ids=sorted({r['run'] for r in rows});names=sorted(set.intersection(*[set(r['features']) for r in rows])) if rows else [];stats=[]
 y=np.array([np.mean([r['C'] for r in rows if r['run']==i]) for i in ids]);rng=np.random.default_rng(20260910);exact=len(ids)<=8;perms=np.array(list(permutations(range(len(ids))))) if exact else np.array([rng.permutation(len(ids)) for _ in range(9999)])
 if len(ids)<4:return dict(bags=len(ids),windows=len(rows),ranking=[],note='Fewer than four independent bags; no ranking.')
 for n in names:
  x=np.array([np.mean([r['features'][n] for r in rows if r['run']==i]) for i in ids]);rr=rho(x,y)
  xr=rankdata(x);yr=rankdata(y);xr-=xr.mean();yr-=yr.mean();den=np.linalg.norm(xr)*np.linalg.norm(yr)
  hits=np.sum(np.abs(yr[perms]@xr/den)>=abs(rr)-1e-12) if den>0 else len(perms)
  pv=float(hits/len(perms) if exact else (1+hits)/(1+len(perms)))
  leave=[rho(np.delete(x,i),np.delete(y,i)) for i in range(len(ids))]
  xm={i:float(x[k]) for k,i in enumerate(ids)};ym={i:float(y[k]) for k,i in enumerate(ids)}
  repeated=[r for r in rows if sum(s['run']==r['run'] for s in rows)>=2]
  within=rho([r['features'][n]-xm[r['run']] for r in repeated],[r['C']-ym[r['run']] for r in repeated]) if len(repeated)>=4 else None
  stats.append(dict(feature=n,within_bag_centered_spearman=within,bag_spearman=rr,pooled_spearman=rho([r['features'][n] for r in rows],[r['C'] for r in rows]),p=pv,leave_min=min(leave),leave_max=max(leave)))
 order=np.argsort([r['p'] for r in stats]);q=1.
 for j in range(len(order)-1,-1,-1):
  i=order[j];q=min(q,stats[i]['p']*len(stats)/(j+1));stats[i]['fdr_q']=q
 stats.sort(key=lambda r:abs(r['bag_spearman']),reverse=True)
 return dict(bags=len(ids),windows=len(rows),ranking=stats,bag_C=[dict(run=i,C=float(y[k]),n=sum(r['run']==i for r in rows)) for k,i in enumerate(ids)])

def main():
 audits,candidates=extract();(OUT/'audit.json').write_text(json.dumps(dict(config=CONFIG,runs=audits,candidates=candidates),indent=2))
 results={}
 for tier in ['strict','screened']:
  rows=select(candidates,tier);(OUT/(tier+'_windows.json')).write_text(json.dumps(rows,indent=2))
  for speed in [.1,.3,.5]:results[tier+'_'+str(speed)]=correlations([r for r in rows if r['speed']==speed])
 (OUT/'correlations.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2)[:6000])
if __name__=='__main__':main()
