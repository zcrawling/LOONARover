"""Offline low-frequency longitudinal consistency; explicitly conditional on fixed tilt."""
import argparse,csv,json,sys
from pathlib import Path
import numpy as np
from scipy.signal import butter,sosfiltfilt,savgol_filter
from scipy.stats import spearmanr
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/odom_v1'))
from analyze import writecsv,stamp,ranges

def derive(t,v,a,cutoff=2.):
 dt=float(np.median(np.diff(t)));hz=1/dt;sos=butter(3,cutoff,fs=hz,output='sos');vs=sosfiltfilt(sos,v)
 n=max(5,int(round(.21*hz))|1);ae=savgol_filter(vs,n,2,deriv=1,delta=dt);ai=sosfiltfilt(sos,a)
 return vs,ae,ai

def lagcheck(t,ae,ai,mask):
 lags=np.arange(-.3,.301,.01);scores=[]
 for lag in lags:
  keep=mask&(t+lag>=t[0])&(t+lag<=t[-1]);x=ae[keep];y=np.interp(t[keep]+lag,t,ai)
  scores.append(float(np.corrcoef(x,y)[0,1]) if len(x)>30 and min(np.std(x),np.std(y))>.005 else -1.)
 k=int(np.argmax(scores));return dict(lag_s=float(lags[k]),correlation=scores[k],boundary=k in [0,len(lags)-1],lags=lags.tolist(),correlations=scores)

def candidate(a,b,minimum):
 rms=float(np.sqrt(np.mean(a*a)));return (float(a@b/(a@a)) if rms>=minimum else None),rms

def load_gt(path):
 state=path/'test.json';meta=path/'camera/capture.json';frames=path/'camera/frames.csv'
 if not all(x.exists() for x in [state,meta,frames]):return None,'missing_GT'
 s=json.loads(state.read_text());m=json.loads(meta.read_text());before=s.get('clock_before',{}).get('best');after=s.get('clock_after',{}).get('best')
 if not before or not after or abs(after['offset_s']-before['offset_s'])>.1:return None,'GT_clock_unverified'
 if m.get('forward_axis')!='x':return None,'GT_axis_unverified'
 rows=[]
 for r in csv.DictReader(frames.open()):
  if r['valid']!='1' or not r['s_m'] or float(r['reprojection_px'])>1.5:continue
  local=float(r['t'])-m.get('time_offset_s',0);t=local+np.interp(local,[before['local_epoch'],after['local_epoch']],[before['offset_s'],after['offset_s']]);rows.append([t,float(r['s_m'])])
 return np.array(rows),'projection_GT_only'

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'data/imu_vibration/odom_v2_analysis');p.add_argument('--cutoff',type=float,default=2.);p.add_argument('--window',type=float,default=1.);p.add_argument('--excitation-rms',type=float,default=.03);p.add_argument('--score-threshold',type=float,default=3.);args=p.parse_args()
 if not 0<args.cutoff<20 or args.window<=0 or args.excitation_rms<=0:p.error('invalid filter/window/excitation')
 out=args.output;out.mkdir(parents=True,exist_ok=True);(out/'series').mkdir(exist_ok=True)
 v1=json.loads((ROOT/'data/imu_vibration/odom_v1_analysis/results.json').read_text());runs=[];audits=[]
 for r in v1['runs']:
  if r['status']!='processed':audits.append(dict(run_id=r['run_id'],status=r['status']));continue
  rid=r['run_id'];base=np.genfromtxt(ROOT/'data/imu_vibration/odom_v1_analysis/series'/f'{rid}.csv',names=True,delimiter=',');raw=[]
  with AnyReader([Path(r['path'])],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
   topics=[c.topic for c in bag.connections]
   for c,ts,d in bag.messages(connections=[c for c in bag.connections if c.topic=='/imu']):
    m=bag.deserialize(d,c.msgtype);raw.append([stamp(m),m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.orientation.x,m.orientation.y,m.orientation.z,m.orientation.w,m.orientation_covariance[0]])
  raw=np.array(raw);rotation=np.array(r['imu_to_base_rotation']);acc=raw[:,1:4]@rotation.T
  t=base['t_ros'];aa=np.column_stack([np.interp(t,raw[:,0],acc[:,j]) for j in range(3)]);static=base['static']>0
  start_static=static&(base['elapsed_s']<5)
  # Use initial rest only; no dynamic high-pass masquerading as gravity compensation.
  if start_static.sum()<30:audits.append(dict(run_id=rid,status='no_initial_accel_reference'));continue
  reference=np.mean(aa[start_static],axis=0);proxy=aa[:,0]-reference[0];ae=np.full(len(t),np.nan);ai=ae.copy();vs=ae.copy();good=np.zeros(len(t),bool)
  for seg in np.unique(base['segment']):
   ids=np.flatnonzero(base['segment']==seg)
   if len(ids)<220:continue
   vs[ids],ae[ids],ai[ids]=derive(t[ids],base['vx_encoder'][ids],proxy[ids],args.cutoff)
   good[ids]=True;good[ids[:100]]=False;good[ids[-100:]]=False
  moving=abs(vs)>.01;excite=good&(abs(ae)>.02);lag=lagcheck(t,ae,ai,excite)
  # Held-out normal references are selected by existing no-slip metadata, not residual/GT.
  normal=rid in ['20260905_160429_188143_forward_2m_01','20260905_160739_205093_reverse_2m_01']
  runs.append(dict(meta=r,base=base,t=t,ae=ae,ai=ai,vs=vs,good=good,static=static,moving=moving,lag=lag,normal=normal,reference=reference.tolist(),yaw_only=bool(np.max(abs(raw[:,4:6]))<1e-8),acc_norm=float(np.median(np.linalg.norm(acc,axis=1))),topics=topics))
 refs=[r for r in runs if r['normal']];lagrefs=[r for r in refs if r['lag']['correlation']>.6 and not r['lag']['boundary']];delay=float(np.median([r['lag']['lag_s'] for r in lagrefs])) if len(lagrefs)>=2 and np.ptp([r['lag']['lag_s'] for r in lagrefs])<=.05 else 0.
 # Delay is a reference-calibrated apparent signal lag, never GT optimized or fitted per target.
 normal_values=[]
 for r in runs:
  r['aligned_ai']=np.interp(r['t']+delay,r['t'],r['ai'],left=np.nan,right=np.nan);r['res']=r['ae']-r['aligned_ai']
  if r['normal']:normal_values.extend(r['res'][r['good']&np.isfinite(r['res'])])
 sigma=float(np.std(normal_values));sigma=max(sigma,1e-4);windows=[];summaries=[]
 for r in runs:
  b=r['base'];t=r['t'];rid=r['meta']['run_id'];score=abs(r['res'])/sigma;gtpath=Path(r['meta']['path']).parent;gtpath=gtpath.parent if gtpath.name=='rover' else gtpath;gt,gtstatus=load_gt(gtpath)
  rows=[];cs=np.full(len(t),np.nan);observable=np.zeros(len(t),bool);distance=np.r_[0,np.cumsum(np.diff(t)*(b['vx_encoder'][1:]+b['vx_encoder'][:-1])/2)]
  for seg in np.unique(b['segment']):
   ii=np.flatnonzero((b['segment']==seg)&r['good'])
   if len(ii)<2:continue
   for left in np.arange(t[ii[0]],t[ii[-1]]-args.window+1e-7,args.window):
    right=left+args.window;sel=(t>=left)&(t<right)&r['good'];n=sel.sum()
    if n<args.window*95 or not np.all(np.isfinite(r['res'][sel])):continue
    c,rms=candidate(r['ae'][sel],r['aligned_ai'][sel],args.excitation_rms);observable[sel]=c is not None
    if c is not None:cs[sel]=c
    w=dict(run_id=rid,start_ros=float(left),end_ros=float(right),a_encoder_rms=rms,excitation='EXCITED' if c is not None else 'UNOBSERVABLE',gravity_status='UNVERIFIED_FIXED_TILT_PROXY',C_accel=c,score_mean=float(np.mean(score[sel])),residual_rms=float(np.sqrt(np.mean(r['res'][sel]**2))),reference_run=r['normal'],C_GT=None,gt_status=gtstatus)
    if gt is not None and len(gt)>2 and gt[0,0]<=left and gt[-1,0]>=right:
     j=max(0,np.searchsorted(gt[:,0],left)-1);k=min(len(gt),np.searchsorted(gt[:,0],right)+1);g=gt[j:k];ds=float(np.interp(right,t,distance)-np.interp(left,t,distance))
     if len(g)>3 and np.max(np.diff(g[:,0]))<=.25 and abs(ds)>=.02:
      w['C_GT']=float((np.interp(right,g[:,0],g[:,1])-np.interp(left,g[:,0],g[:,1]))/ds)
    windows.append(w)
  for i in range(len(t)):
   rows.append(dict(t_ros=t[i],elapsed_s=b['elapsed_s'][i],valid=int(r['good'][i]),vx_encoder=b['vx_encoder'][i],vx_smoothed=r['vs'][i],a_encoder=r['ae'][i],a_imu_x_fixed_tilt_proxy=r['aligned_ai'][i],residual=r['res'][i],score_long=score[i],observability='EXCITED_GRAVITY_UNVERIFIED' if observable[i] else 'UNOBSERVABLE',C_accel=cs[i] if observable[i] else '',v1_yaw=b['yaw_v1'][i]))
  writecsv(out/'series'/f'{rid}.csv',rows)
  ok=r['good']&np.isfinite(r['res']);ex=ok&(abs(r['ae'])>.02)
  summaries.append(dict(run_id=rid,status='conditional_proxy_only',normal_reference=r['normal'],initial_acceleration_base=r['reference'],median_acceleration_norm=r['acc_norm'],orientation_yaw_only=r['yaw_only'],lag_diagnostic=r['lag'],excited_correlation=float(np.corrcoef(r['ae'][ex],r['aligned_ai'][ex])[0,1]) if ex.sum()>30 else None,residual_rms=float(np.sqrt(np.mean(r['res'][ok]**2))),score_gt_threshold_fraction=float(np.mean(score[ok]>args.score_threshold)),v1_yaw_deg=r['meta']['v1_yaw_deg'],topics=r['topics']))
 writecsv(out/'windows.csv',windows)
 paired=[w for w in windows if w['C_GT'] is not None and w['C_accel'] is not None and not w['reference_run']]
 def rho(x,y):
  return float(spearmanr(x,y).statistic) if len(x)>3 and np.std(x)>0 and np.std(y)>0 else None
 stats=dict(n_paired_excited=len(paired),paired_runs=len(set(w['run_id'] for w in paired)),C_spearman=rho([w['C_accel'] for w in paired],[w['C_GT'] for w in paired]),score_mismatch_spearman=rho([w['score_mean'] for w in paired],[abs(w['C_GT']-1) for w in paired]))
 result=dict(config={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},sigma_normal=sigma,delay_applied_s=delay,delay_reference_count=len(lagrefs),delay_note='Apparent lag applied only if both normal references correlate >0.6, non-boundary, lag spread <=50ms. Zero otherwise; not proof of zero hardware latency.',stats=stats,runs=summaries,audit=audits)
 (out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['runs','audit']},indent=2));print('processed',len(summaries),'excluded',len(audits),'windows',len(windows),flush=True)
if __name__=='__main__':main()
