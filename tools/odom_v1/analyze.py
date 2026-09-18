"""LIMO 4WD differential/skid-steer odometry V1: offline encoder vx + corrected gyro wz."""
import argparse,csv,json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'common/ros2/loonar_localization'))
from loonar_localization.integration import integrate_trajectory as integrate

def writecsv(path,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r)) or ['status']
 with path.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def stamp(m):return m.header.stamp.sec+m.header.stamp.nanosec*1e-9
def yaw(q):return float(np.arctan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
def ranges(mask):
 z=np.diff(np.r_[False,mask,False].astype(int));return list(zip(np.flatnonzero(z==1),np.flatnonzero(z==-1)))
def readbag(path):
 im=[];w=[];command=[];trans={};frame=None
 with AnyReader([path],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as b:
  for c,t,d in b.messages(connections=[c for c in b.connections if c.topic in ['/imu','/wheel/odom','/tf_static','/cmd_vel']]):
   m=b.deserialize(d,c.msgtype)
   if c.topic=='/imu':
    frame=m.header.frame_id;im.append([stamp(m),m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z,t/1e9])
   elif c.topic=='/wheel/odom':w.append([stamp(m),m.twist.twist.linear.x,m.twist.twist.angular.z,m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),t/1e9])
   elif c.topic=='/cmd_vel':command.append([t/1e9,m.linear.x,m.angular.z])
   else:
    for tr in m.transforms:
     q=tr.transform.rotation;trans[(tr.header.frame_id,tr.child_frame_id)]=[q.x,q.y,q.z,q.w]
 if len(im)<10 or len(w)<10:return None,'missing_imu_or_wheel'
 im=np.array(im);w=np.array(w);command=np.array(command)
 if any(np.any(np.diff(a[:,0])<=0) for a in [im,w]):return None,'nonmonotonic_header_time'
 if frame=='base_link':R=np.eye(3)
 elif ('base_link',frame) in trans:R=Rotation.from_quat(trans[('base_link',frame)]).as_matrix()
 else:return None,'missing_imu_to_base_rotation'
 im[:,1:4]=im[:,1:4]@R.T
 # Prefer publisher-side ROS timestamps where available, not bag receive times.
 event_path=path.parent/'command-events.jsonl'
 source='bag receipt (/cmd_vel has no header)'
 if event_path.exists():
  events=[json.loads(x) for x in event_path.read_text().splitlines()]
  command=np.array([[e['ros_stamp_ns']/1e9,e['linear_mps'],e['angular_radps']] for e in events]);source='command event publication ROS timestamp'
 if len(command)<1:return None,'no_command_context_for_static_bias'
 return dict(im=im,w=w,cmd=command,cmd_source=source,frame=frame,imu_rotation=R.tolist()),None

def aligned(data,args):
 im=data['im'].copy();im[:,0]-=args.gyro_delay;w=data['w'];lo=max(im[0,0],w[0,0]);hi=min(im[-1,0],w[-1,0]);t=np.arange(lo,hi,1/args.hz)
 out={}
 valid=np.ones(len(t),bool)
 for key,a,gap in [('imu',im,.04),('wheel',w,.08)]:
  j=np.clip(np.searchsorted(a[:,0],t),1,len(a)-1);valid&=(a[j,0]-a[j-1,0])<=gap
  out[key]=np.column_stack([np.interp(t,a[:,0],a[:,k]) for k in range(1,a.shape[1])])
 j=np.searchsorted(data['cmd'][:,0],t,side='right')-1;cmdvalid=j>=0;j=np.clip(j,0,len(data['cmd'])-1);cmd=data['cmd'][j,1:3]
 static=valid&cmdvalid&(abs(cmd[:,0])<1e-7)&(abs(cmd[:,1])<1e-7)&(abs(out['wheel'][:,0])<args.static_v)&(abs(out['wheel'][:,1])<args.static_w)
 trimmed=np.zeros(len(t),bool)
 for a,b in ranges(static):
  a+=round(args.static_trim*args.hz);b-=round(args.static_trim*args.hz)
  if b-a>=args.min_static_seconds*args.hz:trimmed[a:b]=True
 return t,out['wheel'],out['imu'][:,2],valid,trimmed,cmd

def apparent_lag(t,enc,imu,valid):
 if valid.sum()<100 or np.std(enc[valid])<.02 or np.std(imu[valid])<.005:return dict(status='insufficient_yaw_excitation',applied=False)
 lags=np.arange(-.2,.2001,.01);scores=[]
 for lag in lags:
  ok=valid&(t-lag>=t[0])&(t-lag<=t[-1]);z=np.interp(t[ok]-lag,t,enc);q=imu[ok];scores.append(float(np.corrcoef(z,q)[0,1]) if min(np.std(z),np.std(q))>1e-7 else 0.)
 j=int(np.argmax(scores));return dict(status='apparent_only_not_clock_offset',candidate_gyro_lag_s=float(lags[j]),peak_correlation=scores[j],boundary_peak=j in [0,len(lags)-1],applied=False,note='Wheel yaw can be wrong due to effective track/slip. This is not independent sensor-delay calibration.')

def tag_evaluation(runpath,series):
 frames=runpath/'camera/frames.csv';statefile=runpath/'test.json'
 if not frames.exists() or not statefile.exists():return dict(status='no_AprilTag')
 state=json.loads(statefile.read_text())
 if 'clock_before' not in state or 'clock_after' not in state:return dict(status='no_GT_clock_alignment')
 before=state['clock_before']['best'];after=state['clock_after']['best']
 if abs(after['offset_s']-before['offset_s'])>.1:return dict(status='GT_clock_unstable')
 with frames.open() as f:fr=[r for r in csv.DictReader(f) if r['valid']=='1' and r['s_m'] and float(r['reprojection_px'])<=1.5]
 if len(fr)<2:return dict(status='insufficient_GT')
 meta=json.loads((runpath/'camera/capture.json').read_text());g=[]
 for r in fr:
  local=float(r['t'])-meta.get('time_offset_s',0.);tt=local+np.interp(local,[before['local_epoch'],after['local_epoch']],[before['offset_s'],after['offset_s']]);g.append([tt,float(r['s_m'])])
 g=np.array(g);best=None
 for seg in sorted({r['segment'] for r in series}):
  rr=[r for r in series if r['segment']==seg];t=np.array([r['t_ros'] for r in rr]);gg=g[(g[:,0]>=t[0])&(g[:,0]<=t[-1])]
  if len(gg)<10:continue
  # Match only connected reliable camera intervals, avoiding interpolation over missing GT.
  cuts=np.r_[0,np.flatnonzero(np.diff(gg[:,0])>.25)+1,len(gg)]
  for a,b in zip(cuts[:-1],cuts[1:]):
   z=gg[a:b]
   if len(z)<10 or z[-1,0]-z[0,0]<1:continue
   dur=z[-1,0]-z[0,0]
   if best is not None and dur<=best['duration_s']:continue
   gt=float(z[-1,1]-z[0,1]);de=float(np.interp(z[-1,0],t,[r['x_encoder'] for r in rr])-np.interp(z[0,0],t,[r['x_encoder'] for r in rr]));dv=float(np.interp(z[-1,0],t,[r['x_v1'] for r in rr])-np.interp(z[0,0],t,[r['x_v1'] for r in rr]))
   best=dict(status='longitudinal_projection_only',duration_s=dur,GT_delta_m=gt,encoder_x_delta_m=de,v1_x_delta_m=dv,encoder_x_error_m=de-gt,v1_x_error_m=dv-gt,note='GT is initial-tag-axis projection; assumes initial body forward aligns with tag axis. No signed yaw GT in saved frames; heading_change_deg is unsigned 3D rotation, not planar yaw. GT never affects integration or bias.')
 return best or dict(status='no_long_enough_connected_GT')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'data/imu_vibration/odom_v1_analysis');p.add_argument('--hz',type=float,default=100);p.add_argument('--residual-threshold',type=float,default=.05,help='rad/s, diagnostic only');p.add_argument('--score-floor',type=float,default=.01,help='rad/s');p.add_argument('--residual-window',type=float,default=.25);p.add_argument('--static-v',type=float,default=.005);p.add_argument('--static-w',type=float,default=.01);p.add_argument('--static-trim',type=float,default=.2);p.add_argument('--min-static-seconds',type=float,default=.3);p.add_argument('--gyro-delay',type=float,default=0.,help='Known measurement delay only. Header alignment alone is default.');args=p.parse_args()
 if args.hz<=0 or min(args.residual_threshold,args.score_floor,args.residual_window,args.min_static_seconds)<=0:p.error('rates, thresholds and windows must be positive')
 out=args.output;out.mkdir(parents=True,exist_ok=True);(out/'series').mkdir(exist_ok=True)
 records=[];audits=[];seen=set()
 for metadata in sorted((ROOT/'data').rglob('metadata.yaml')):
  if 'bag'!=metadata.parent.name:continue
  path=metadata.parent;rid=path.parent.parent.name if path.parent.name=='rover' else path.parent.name
  if '173746_028090' in rid:audits.append(dict(run_id=rid,status='user_excluded_uphill'));continue
  dbs=sorted(path.glob('*.db3'));digest=hashlib.sha256(b''.join(x.read_bytes() for x in dbs)).hexdigest() if dbs else str(path)
  if digest in seen:audits.append(dict(run_id=rid,status='duplicate_bag'));continue
  seen.add(digest);data,error=readbag(path)
  if error:audits.append(dict(run_id=rid,status=error));continue
  t,w,g,valid,static,cmd=aligned(data,args);n=int(static.sum())
  record=dict(run_id=rid,path=str(path),data=data,t=t,w=w,g=g,valid=valid,static=static,cmd=cmd)
  # Pre-motion stationary reference first, avoiding calibration with later moving data.
  moving=np.flatnonzero((abs(cmd[:,0])+abs(cmd[:,1]))>1e-7);pre=static.copy()
  if len(moving):pre&=t<t[moving[0]]
  use=pre if pre.sum()>=args.min_static_seconds*args.hz else static
  if use.sum()>=args.min_static_seconds*args.hz:
   record.update(bias=float(np.mean(g[use])),bias_std=float(np.std(g[use])),bias_n=int(use.sum()),bias_source='pre_motion_static' if np.array_equal(use,pre) else 'commanded_static_offline')
  else:record.update(bias=None,bias_source='unavailable')
  records.append(record)
 # No arbitrary zero-bias fallback. Only a nearby same-day measured reference is allowed.
 for r in records:
  if r['bias'] is None:
   others=[s for s in records if s['bias'] is not None and not s['bias_source'].startswith('nearby_static_reference:') and abs(s['t'][0]-r['t'][0])<3600]
   if others:
    s=min(others,key=lambda s:abs(s['t'][0]-r['t'][0]));r.update(bias=s['bias'],bias_std=s['bias_std'],bias_n=s['bias_n'],bias_source='nearby_static_reference:'+s['run_id'])
  if r['bias'] is None:audits.append(dict(run_id=r['run_id'],status='no_supported_static_bias'));continue
  t,w,g,valid,static,cmd=(r[k] for k in ['t','w','g','valid','static','cmd']);v=w[:,0];we=w[:,1];wi=g-r['bias'];res=we-wi
  serial=[];segments=ranges(valid);final_dyaw=0.;max_dyaw=0.;suspect_n=moving_n=0;count=0;enc_total=imu_total=0.
  static_noise=float(np.std(res[static])) if static.sum()>10 else r['bias_std'];denom=max(static_noise,args.score_floor)
  for seg,(a,b) in enumerate(segments):
   if b-a<2:continue
   te=t[a:b];pe=integrate(te,v[a:b],we[a:b]);pi=integrate(te,v[a:b],wi[a:b]);window=max(1,round(args.residual_window*args.hz));cum=np.r_[0,np.cumsum(res[a:b])];idx=np.arange(b-a);starts=np.maximum(0,idx-window+1);mean=(cum[idx+1]-cum[starts])/(idx-starts+1)
   active=(abs(cmd[a:b,0])+abs(cmd[a:b,1])>1e-7)| (abs(v[a:b])>.005);suspect=active&(abs(mean)>args.residual_threshold);suspect_n+=int(suspect.sum());moving_n+=int(active.sum())
   final_dyaw+=float(pe[-1,2]-pi[-1,2]);enc_total+=pe[-1,2];imu_total+=pi[-1,2];max_dyaw=max(max_dyaw,float(np.max(abs(pe[:,2]-pi[:,2]))))
   # Preserve recorded baseline pose, rebased by its own initial heading.
   original=np.unwrap(w[a:b,4]);originyaw=original[0];dx=w[a:b,2]-w[a,2];dy=w[a:b,3]-w[a,3];ox=dx*np.cos(originyaw)+dy*np.sin(originyaw);oy=-dx*np.sin(originyaw)+dy*np.cos(originyaw)
   for j,k in enumerate(range(a,b)):
    serial.append(dict(t_ros=float(t[k]),elapsed_s=float(t[k]-t[0]),segment=seg,valid=1,vx_encoder=float(v[k]),vx_corrected=float(v[k]),wz_encoder=float(we[k]),wz_imu_raw=float(g[k]),gyro_bias=r['bias'],wz_imu=float(wi[k]),yaw_residual=float(res[k]),residual_mean=float(mean[j]),normalized_score=float(abs(mean[j])/denom),suspect=int(suspect[j]),static=int(static[k]),x_encoder=pe[j,0],y_encoder=pe[j,1],yaw_encoder=pe[j,2],x_v1=pi[j,0],y_v1=pi[j,1],yaw_v1=pi[j,2],recorded_x=ox[j],recorded_y=oy[j],recorded_yaw=float(original[j]-original[0])))
  if not serial:continue
  writecsv(out/'series'/f"{r['run_id']}.csv",serial)
  # Nearest header sample phase is sampling alignment, not a sensor latency estimate.
  im=r['data']['im'];ww=r['data']['w'];j=np.clip(np.searchsorted(im[:,0],ww[:,0]),1,len(im)-1);choose=np.where(abs(im[j,0]-ww[:,0])<abs(im[j-1,0]-ww[:,0]),j,j-1);phase=im[choose,0]-ww[:,0]
  active=valid&((abs(cmd[:,0])+abs(cmd[:,1])>1e-7)|(abs(v)>.005))
  runpath=Path(r['path']).parent.parent if Path(r['path']).parent.name=='rover' else Path(r['path']).parent
  result=dict(run_id=r['run_id'],path=r['path'],status='processed',duration_s=float(t[-1]-t[0]),segments=len(segments),gap_seconds=float((~valid).sum()/args.hz),bias_radps=r['bias'],bias_degps=float(np.degrees(r['bias'])),static_std_degps=float(np.degrees(r['bias_std'])),static_seconds=r['bias_n']/args.hz,bias_source=r['bias_source'],imu_to_base_rotation=r['data']['imu_rotation'],command_timestamp_source=r['data']['cmd_source'],header_phase_median_ms=float(np.median(phase)*1000),header_phase_abs_p95_ms=float(np.percentile(abs(phase),95)*1000),imu_receive_minus_header_median_ms=float(np.median(im[:,-1]-im[:,0])*1000),wheel_receive_minus_header_median_ms=float(np.median(ww[:,-1]-ww[:,0])*1000),lag_diagnostic=apparent_lag(t,we,wi,valid),encoder_yaw_deg=float(np.degrees(enc_total)),v1_yaw_deg=float(np.degrees(imu_total)),yaw_difference_deg=float(np.degrees(final_dyaw)),max_yaw_difference_deg=float(np.degrees(max_dyaw)),active_residual_rms_degps=float(np.degrees(np.sqrt(np.mean(res[active]**2)))) if active.any() else 0.,suspect_fraction=float(suspect_n/max(1,moving_n)),static_residual_std_radps=static_noise,score_denominator_radps=denom,gt=tag_evaluation(runpath,serial),pose_scope='common header-time interval; origin reset at sensor gaps, no integration across gaps')
  # Existing manual GT is approximate and sign is taken only from explicit turn label.
  trial=runpath/'trial.yaml'
  if trial.exists():
   result['manual_trial_text']=trial.read_text()
   if '30deg' in r['run_id'] and '28' in trial.read_text():
    gt=-28. if 'right' in r['run_id'] else 28.;result['manual_yaw_gt']=dict(deg=gt,quality='user approx 28 degrees, explicitly large measurement error',encoder_error_deg=result['encoder_yaw_deg']-gt,v1_error_deg=result['v1_yaw_deg']-gt)
  audits.append(result);print(r['run_id'],'enc',round(result['encoder_yaw_deg'],2),'v1',round(result['v1_yaw_deg'],2),'bias',round(result['bias_degps'],4),flush=True)
 config={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()};(out/'results.json').write_text(json.dumps(dict(config=config,runs=audits,notes=['LIMO 4WD skid-steer, not final LOONAR geometry.','vx is unchanged; no common-mode longitudinal correction.','Residual flags are slip suspects, also explained by wheel scales/effective separation/timing/quantization.','GT is evaluation-only; no GT calibration of yaw, velocity, or gyro bias.']),indent=2))
 flat=[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in audits];writecsv(out/'summary.csv',flat)
 print('Saved',out)
if __name__=='__main__':main()
