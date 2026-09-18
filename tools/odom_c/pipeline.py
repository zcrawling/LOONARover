"""Offline paired-window C_GT dataset. Never publishes commands or changes odometry."""
import argparse,csv,json,sys
from pathlib import Path
from collections import Counter
import numpy as np
from scipy import signal,stats
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/apriltag_gt'))
from loonar_apriltag.trial_analysis import motion_intervals

IMU_NAMES=['ax','ay','az','gx','gy','gz']
STATE=['vx_mean','vx_std','left_mean','right_mean','wz_mean','wheel_accel_rms']
CORE={k:[k+'_az_std',k+'_ax_rms',k+'_az_kurtosis',k+'_gz_rms']+STATE for k in ['raw','detrended']}

def write_csv(path,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields or ['status']);w.writeheader();w.writerows(rows)
def stamp(m):return m.header.stamp.sec+m.header.stamp.nanosec*1e-9
def integral(t,v):return np.r_[0,np.cumsum(np.diff(t)*(v[:-1]+v[1:])/2)]
def delta(t,s,a,b):return float(np.interp(b,t,s)-np.interp(a,t,s))
def robust_line(t,s):
 x=t-t.mean();A=np.column_stack([np.ones(len(x)),x]);beta=np.linalg.lstsq(A,s,rcond=None)[0]
 for _ in range(5):
  res=s-A@beta;scale=max(1e-6,1.4826*np.median(np.abs(res-np.median(res))));w=np.minimum(1,1.345*scale/np.maximum(abs(res),1e-12));beta=np.linalg.lstsq(A*np.sqrt(w[:,None]),s*np.sqrt(w),rcond=None)[0]
 return beta,float(np.sqrt(np.mean((s-A@beta)**2)))
def covered(t,a,b,gap):
 inside=t[(t>a)&(t<b)]
 return len(t)>1 and t[0]<=a and t[-1]>=b and np.max(np.diff(np.r_[a,inside,b]))<=gap

def summarize(x):
 centered=x-x.mean();sd=x.std()
 return dict(mean=float(x.mean()),std=float(sd),rms=float(np.sqrt(np.mean(x*x))),ptp=float(np.ptp(x)),mad=float(np.median(abs(x-np.median(x)))),skewness=float(np.mean(centered**3)/sd**3) if sd>1e-12 else 0.,kurtosis=float(np.mean(centered**4)/sd**4) if sd>1e-12 else 0.,diff_rms=float(np.sqrt(np.mean(np.diff(x)**2))),energy=float(np.mean(x*x)))
def features(imu,wheel):
 result={}
 for mode,arr in [('raw',imu),('detrended',signal.detrend(imu,axis=0,type='linear'))]:
  for name,x in zip(IMU_NAMES,arr.T):
   result.update({mode+'_'+name+'_'+k:v for k,v in summarize(x).items()})
 vx,wz,left,right=wheel.T
 result.update(vx_mean=float(vx.mean()),vx_std=float(vx.std()),left_mean=float(left.mean()),right_mean=float(right.mean()),wz_mean=float(wz.mean()),wheel_accel_rms=float(np.sqrt(np.mean(np.diff(vx)**2)))*100)
 return result

def estimate_motion_lag(camera,wheel):
 """Apparent lag only: cannot separate wheel slip/dynamics from optical delay."""
 if len(camera)<12 or len(wheel)<20:return dict(status='insufficient_data',applied=False)
 lo=max(camera[0,0],wheel[0,0])+.6;hi=min(camera[-1,0],wheel[-1,0])-.6
 tt=np.arange(lo,hi,.05)
 if len(tt)<20:return dict(status='insufficient_overlap',applied=False)
 vel=[]
 for t in tt:
  g=camera[(camera[:,0]>=t-.2)&(camera[:,0]<=t+.2)]
  vel.append(robust_line(g[:,0],g[:,1])[0][1] if len(g)>=4 and np.max(np.diff(g[:,0]))<.15 else np.nan)
 vel=np.array(vel);ok=np.isfinite(vel);tt=tt[ok];vel=vel[ok]
 if len(tt)<20 or np.std(vel)<.005:return dict(status='insufficient_excitation',applied=False)
 delays=np.arange(-.5,.501,.025);corr=[]
 for delay in delays:
  v=np.interp(tt-delay,wheel[:,0],wheel[:,1]);corr.append(float(np.corrcoef(vel,v)[0,1]) if v.std()>.005 else 0.)
 idx=int(np.argmax(corr));peak=corr[idx];prom=peak-float(np.median(corr))
 return dict(status='apparent_lag_candidate' if peak>.6 and prom>.1 and idx not in [0,len(delays)-1] else 'not_identifiable',candidate_camera_lag_s=float(delays[idx]),peak_correlation=peak,peak_minus_median=prom,applied=False,note='Correlation combines camera receipt delay, actual wheel/body dynamics and slip; not an exposure-delay calibration.')

def terrain_at(meta,run,a,b):
 # Only explicit metadata. No terrain inference from run ID or vibration.
 entry=meta.get(run,{})
 for seg in entry.get('intervals',[]):
  if a>=seg['start_ros'] and b<=seg['end_ros']:return seg['terrain_id']
 if any(a<seg['end_ros'] and b>seg['start_ros'] for seg in entry.get('intervals',[])):return 'mixed'
 return entry.get('terrain_id','unknown')

def load_run(p,args):
 paths=list(p.glob('**/bag/metadata.yaml'));audit=dict(run_id=p.name,path=str(p.relative_to(ROOT)))
 if not paths or not (p/'camera/frames.csv').exists():return None,{**audit,'status':'missing_bag_or_GT'}
 state=json.loads((p/'test.json').read_text());meta=json.loads((p/'camera/capture.json').read_text())
 if 'clock_before' not in state:return None,{**audit,'status':'missing_clock_measurement'}
 if meta.get('forward_axis')!='x':return None,{**audit,'status':'unverified_progress_axis'}
 before=state['clock_before']['best'];after=state.get('clock_after',{}).get('best')
 if after is None:return None,{**audit,'status':'missing_post_clock_measurement'}
 change=after['offset_s']-before['offset_s'];audit.update(clock_offset_before_s=before['offset_s'],clock_offset_after_s=after['offset_s'],clock_change_s=change,clock_rtt_s=max(before['rtt_s'],after['rtt_s']),camera_timestamp='host receipt, not exposure',camera_delay_applied_s=args.camera_delay,speed_command=state.get('speed_mps'),focus=meta.get('focus_lock'),axis='initial tag +X; body translation only under straight fixed-mount assumption')
 if abs(change)>args.max_clock_change:return None,{**audit,'status':'clock_change_exceeds_limit'}
 event_path=paths[0].parent.parent/'command-events.jsonl'
 if not event_path.exists():return None,{**audit,'status':'missing_command_timeline'}
 events=[json.loads(l) for l in event_path.read_text().splitlines()];command=np.array([[e['ros_stamp_ns']/1e9,e['linear_mps'],e['angular_radps']] for e in events]);intervals=motion_intervals(events,args.settle,args.stop_guard)
 im=[];wh=[];pos=[]
 with AnyReader([paths[0].parent],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
  audit['topics']=[c.topic for c in bag.connections]
  for c,received,data in bag.messages(connections=[c for c in bag.connections if c.topic in ['/imu','/wheel/odom','/wheel/odometer']]):
   m=bag.deserialize(data,c.msgtype);t=stamp(m)
   if c.topic=='/imu':im.append([t,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
   elif c.topic=='/wheel/odom':wh.append([t,m.twist.twist.linear.x,m.twist.twist.angular.z])
   elif len(m.position)>=2:pos.append([t,*m.position[:2]])
 im=np.array(im);wh=np.array(wh);pos=np.array(pos)
 if min(len(im),len(wh),len(pos))<5:return None,{**audit,'status':'missing_sensor_channels'}
 if any(np.any(np.diff(x[:,0])<=0) for x in [im,wh,pos]):return None,{**audit,'status':'nonmonotonic_sensor_stamps'}
 # Position differences are interval-average velocity, timestamped at interval midpoint.
 rates=np.column_stack([(pos[1:,0]+pos[:-1,0])/2,np.diff(pos[:,1:],axis=0)/np.diff(pos[:,0])[:,None]])
 with (p/'camera/frames.csv').open() as f:fr=list(csv.DictReader(f))
 gt=[];alltimes=[]
 for r in fr:
  local=float(r['t'])-meta.get('time_offset_s',0.)
  t=local+np.interp(local,[before['local_epoch'],after['local_epoch']],[before['offset_s'],after['offset_s']])-args.camera_delay
  alltimes.append(t)
  if r['valid']=='1' and r['s_m']:
   gt.append([t,float(r['s_m']),float(r['reprojection_px']),float(r['heading_change_deg']),float(r.get('decision_margin') or 'nan'),float(r.get('hamming') or 'nan'),float(r['x']),float(r['y']),float(r['z'])])
 gt=np.array(gt)
 if len(gt)<5:return None,{**audit,'status':'insufficient_GT'}
 if np.any(np.diff(gt[:,0])<=0):return None,{**audit,'status':'nonmonotonic_GT'}
 audit.update(status='loaded',imu_hz=float(1/np.median(np.diff(im[:,0]))),apparent_lag=estimate_motion_lag(gt,wh),motor_current='not recorded',terrain_id='unknown unless metadata supplied')
 return dict(im=im,wh=wh,rates=rates,gt=gt,alltimes=np.array(alltimes),command=command,intervals=intervals),audit

def synchronized(data,path):
 start=max(data[k][0,0] for k in ['im','wh','rates','gt']);end=min(data[k][-1,0] for k in ['im','wh','rates','gt']);tt=np.arange(start,end,.01)
 columns={'t_ros':tt}
 for key,names,maxgap in [('im',IMU_NAMES,.04),('wh',['vx','wz'],.08),('rates',['left_velocity','right_velocity'],.08),('gt',['tag_progress','reprojection','heading','decision_margin','hamming','tag_x','tag_y','tag_z'],.25)]:
  a=data[key];idx=np.clip(np.searchsorted(a[:,0],tt),1,len(a)-1);valid=(a[idx,0]-a[idx-1,0])<=maxgap
  columns[key+'_valid']=valid.astype(int)
  columns[key+'_measurement_before']=a[idx-1,0];columns[key+'_measurement_after']=a[idx,0]
  for j,n in enumerate(names,1):
   value=np.interp(tt,a[:,0],a[:,j])
   if n in ['reprojection','hamming']:value=np.maximum(a[idx-1,j],a[idx,j])
   elif n=='decision_margin':value=np.minimum(a[idx-1,j],a[idx,j])
   columns[n]=np.where(valid,value,np.nan)
 idx=np.clip(np.searchsorted(data['command'][:,0],tt,side='right')-1,0,len(data['command'])-1)
 columns['cmd_vx']=data['command'][idx,1];columns['cmd_wz']=data['command'][idx,2]
 write_csv(path,[dict(zip(columns,vals)) for vals in zip(*columns.values())])

def windows(data,run,args,terrain,audit):
 im,w,rates,g=(data[k] for k in ['im','wh','rates','gt']);distance=integral(w[:,0],w[:,1]);rejected=[];accepted=[];spectra=[]
 for seg,(left,right) in enumerate(data['intervals']):
  for end in np.arange(left+args.window,right+1e-7,args.step):
   start=end-args.window;row=dict(run_id=run,terrain_id=terrain_at(terrain,run,start,end),segment=seg,timestamp_start=float(start),timestamp_end=float(end),window_s=args.window)
   why=[]
   for key,gap in [('im',.04),('wh',.08),('rates',.08)]:
    if not covered(data[key][:,0],start,end,gap):why.append(key+'_gap')
   gg=g[(g[:,0]>=start)&(g[:,0]<=end)]
   total=np.sum((data['alltimes']>=start)&(data['alltimes']<=end))
   if len(gg)<args.min_tag_samples:why.append('too_few_GT')
   elif max(np.diff(np.r_[start,gg[:,0],end]))>args.tag_gap or gg[0,0]-start>.1 or end-gg[-1,0]>.1:why.append('GT_gap_or_endpoint_support')
   if len(gg)/max(1,total)<.9:why.append('GT_fraction')
   ii=im[(im[:,0]>=start)&(im[:,0]<=end)]
   if len(ii)<.85*100*args.window:why.append('imu_rate')
   commands=data['command'][(data['command'][:,0]>=start)&(data['command'][:,0]<=end)]
   if len(commands)==0 or np.max(abs(commands[:,2]))>1e-6:why.append('nonstraight_command')
   if why:rejected.append({**row,'reason':'|'.join(why)});continue
   enc=delta(w[:,0],distance,start,end);row['Delta_s_encoder']=enc
   if abs(enc)<args.epsilon:rejected.append({**row,'reason':'small_encoder_distance_stationary'});continue
   if np.max(gg[:,2])>args.reprojection or np.ptp(gg[:,3])>args.heading_range:rejected.append({**row,'reason':'GT_pose_quality'});continue
   beta,rms=robust_line(gg[:,0],gg[:,1]);ds=float(beta[1]*args.window);C=ds/enc
   row.update(Delta_s_GT=ds,C_GT=C,GT_fit_rms_m=rms,tag_samples=len(gg),max_reprojection_px=float(gg[:,2].max()),label_method='within-window Huber linear progress fit at t0,t1; no external filter or temporal shift')
   # Residual guard does not reject zero body motion when wheels spin.
   if rms>args.gt_rms:why.append('GT_fit_residual')
   if not args.c_min<=C<=args.c_max:why.append('C_range')
   denominators=[delta(w[:,0],distance,start+s,end+s) for s in [-.1,0,.1] if w[0,0]<=start+s and end+s<=w[-1,0]]
   shifts=[ds/v if abs(v)>1e-9 else float('nan') for v in denominators]
   row['C_time_sensitivity_range']=float(np.ptp(shifts)) if len(shifts)==3 else None
   if len(shifts)!=3 or not np.isfinite(shifts).all() or np.ptp(shifts)>args.c_time_range:why.append('delay_sensitive')
   if why:rejected.append({**row,'reason':'|'.join(why)});continue
   tt=start+np.arange(round(args.window*100))*.01
   imu=np.column_stack([np.interp(tt,im[:,0],im[:,j]) for j in range(1,7)])
   wheel=np.column_stack([np.interp(tt,w[:,0],w[:,1]),np.interp(tt,w[:,0],w[:,2]),np.interp(tt,rates[:,0],rates[:,1]),np.interp(tt,rates[:,0],rates[:,2])])
   row.update(features(imu,wheel));row['speed_bin']=int(np.digitize(row['vx_mean'],args.speed_bins));row['no_slip_label']=int(abs(C-1)<=args.no_slip_tolerance);row['slip_label']=int(C<1-args.slip_threshold)
   accepted.append(row)
  # PSD separately over native valid contiguous chunks, not duplicated sliding windows.
  chunk=im[(im[:,0]>=left)&(im[:,0]<=right)]
  if len(chunk)>=100 and np.max(np.diff(chunk[:,0]))<=.04:
   tt=np.arange(chunk[0,0],chunk[-1,0],.01);v=np.column_stack([np.interp(tt,chunk[:,0],chunk[:,j]) for j in range(1,7)])
   for mode,z in [('raw',v),('detrended',signal.detrend(v,axis=0))]:
    f,P=signal.welch(z,fs=100,nperseg=min(len(z),400),axis=0,detrend=False)
    spectra.extend(dict(run_id=run,segment=seg,mode=mode,frequency_hz=float(ff),**{n:float(pp[j]) for j,n in enumerate(IMU_NAMES)}) for ff,pp in zip(f,P))
 return accepted,rejected,spectra

def parse():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--date',default='20260910');p.add_argument('--window',type=float,default=1.);p.add_argument('--step',type=float,default=.2)
 p.add_argument('--output',type=Path,default=ROOT/'data/apriltag_gt/c_pipeline_20260910');p.add_argument('--terrain-metadata',type=Path)
 p.add_argument('--epsilon',type=float,default=.02);p.add_argument('--settle',type=float,default=2.);p.add_argument('--stop-guard',type=float,default=.5)
 p.add_argument('--tag-gap',type=float,default=.25);p.add_argument('--min-tag-samples',type=int,default=6);p.add_argument('--gt-rms',type=float,default=.003)
 p.add_argument('--reprojection',type=float,default=1.5);p.add_argument('--heading-range',type=float,default=3.)
 p.add_argument('--c-min',type=float,default=-.2);p.add_argument('--c-max',type=float,default=2.);p.add_argument('--c-time-range',type=float,default=.04)
 p.add_argument('--max-clock-change',type=float,default=.1);p.add_argument('--camera-delay',type=float,default=0.,help='Measured camera exposure-to-receipt delay only; zero means uncalibrated, not proven zero')
 p.add_argument('--speed-bins',type=float,nargs='+',default=[0,.075,.15,.25,.4,.6]);p.add_argument('--no-slip-tolerance',type=float,default=.03);p.add_argument('--slip-threshold',type=float,default=.05)
 a=p.parse_args()
 if a.window<.5 or a.step<=0 or a.step>a.window or a.epsilon<=0:p.error('Require window >=0.5s, 0<step<=window, epsilon>0')
 return a

def main():
 args=parse();args.output.mkdir(parents=True,exist_ok=True);(args.output/'synchronized').mkdir(exist_ok=True)
 terrain=json.loads(args.terrain_metadata.read_text()) if args.terrain_metadata else {};samples=[];reject=[];audits=[];psd=[]
 for p in sorted((ROOT/'data/apriltag_gt').rglob('tag_'+args.date+'*')):
  if not p.is_dir():continue
  data,audit=load_run(p,args);audits.append(audit)
  if data is None:print(p.name,audit['status'],flush=True);continue
  synchronized(data,args.output/'synchronized'/f'{p.name}.csv')
  rows,bad,spectra=windows(data,p.name,args,terrain,audit);samples.extend(rows);reject.extend(bad);psd.extend(spectra)
  audit.update(accepted=len(rows),rejected=len(bad),reasons=dict(Counter(r['reason'] for r in bad)))
  print(p.name,len(rows),'accepted',len(bad),'rejected',flush=True)
 write_csv(args.output/'windows.csv',samples);write_csv(args.output/'rejected_windows.csv',reject);write_csv(args.output/'psd.csv',psd)
 config={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
 (args.output/'audit.json').write_text(json.dumps(dict(config=config,runs=audits,core_features=CORE,notes=['No automatic lag correction. Exposure delay remains uncalibrated unless explicitly measured.','Unknown terrain is not a terrain class.','No-slip/slip tags are GT-based provisional evaluation categories, not verified terrain or stuck labels.','Linear detrending compares residuals without inventing a frequency cutoff.']),indent=2))
 template={r['run_id']:{'terrain_id':'unknown','intervals':[]} for r in audits};(args.output/'terrain_template.json').write_text(json.dumps(template,indent=2))
 print('Saved',len(samples),'windows to',args.output)
if __name__=='__main__':main()
