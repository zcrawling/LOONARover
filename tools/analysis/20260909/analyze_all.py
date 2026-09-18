"""Offline audit; preserves failures, excludes the user-specified uphill run."""
from pathlib import Path
import csv,json,re
from collections import Counter
import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parents[3]/'data/apriltag_gt/analysis_20260909'
ROOT=OUT.parent
EXCLUDED='/home/wego/odom_tests/20260909_163750_526566_tag_20260909_173746_028090'
TERRAINS={
 '154757':'indoor','160445':'indoor','160659':'indoor','161123':'indoor','161328':'indoor','162126':'indoor',
 '170820':'rough_paving','170906':'rough_paving','171221':'rough_paving','171256':'rough_paving','171345':'rough_paving','171658':'rough_paving',
 '172131':'stone_asphalt','173007':'stone_asphalt','173106':'stone_asphalt','173236':'stone_asphalt','173315':'stone_asphalt','173427':'stone_asphalt',
 '173636':'pavers','173746':'excluded_uphill','173950':'grass_soil','174117':'grass_soil','174247':'asphalt','174633':'entrance_tiles'}
def readj(p):return json.loads(p.read_text()) if p.exists() else {}
def quant(a):return dict(zip(['min','p05','median','p95','max'],np.quantile(a,[0,.05,.5,.95,1]).tolist())) if len(a) else None
def timing(a):
    dt=np.diff(a[:,0]);return dict(n=len(a),median_hz=float(1/np.median(dt)) if len(dt) and np.median(dt)>0 else None,max_gap_s=float(max(dt)) if len(dt) else None,nonincreasing=int(sum(dt<=0)))
def bagdata(path):
    streams={};counts={}
    with AnyReader([path],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
        counts={c.topic:c.msgcount for c in bag.connections}
        for c,receipt,raw in bag.messages():
            if c.topic not in ['/wheel/odom','/imu','/odometry/filtered','/cmd_vel','/wheel/odometer']:continue
            m=bag.deserialize(raw,c.msgtype)
            t=receipt/1e9 if c.topic=='/cmd_vel' else m.header.stamp.sec+m.header.stamp.nanosec/1e9
            if c.topic in ['/wheel/odom','/odometry/filtered']:
                q=m.pose.pose.orientation
                yaw=np.arctan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                values=[m.twist.twist.linear.x,m.twist.twist.angular.z,m.pose.pose.position.x,m.pose.pose.position.y,yaw]
            elif c.topic=='/imu':
                values=[m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z]
            elif c.topic=='/cmd_vel':values=[m.linear.x,m.angular.z]
            else:values=list(m.position)
            streams.setdefault(c.topic,[]).append([t,*values])
    return {k:np.array(v) for k,v in streams.items()},counts

reports=[];all_windows=[];window_fields=['run_id','terrain','end_t','camera_delta_m','wheel_delta_m','ratio','accel_std_norm','gyro_std_norm']
for p in sorted(ROOT.glob('tag_*')):
    rid=p.name;short=rid[13:19];meta=readj(p/'test.json');capture=readj(p/'camera/capture.json')
    log=(p/'rover.log').read_text() if (p/'rover.log').exists() else ''
    match=re.search(r'^Recording: (/.+)$',log,re.M)
    remote=meta.get('remote_trial_path') or (match.group(1).strip() if match else None)
    r=dict(run_id=rid,short=short,terrain=TERRAINS.get(short,'unknown'),terrain_source='visual first-frame review; no preparation/depth labels',status=meta.get('status','missing_summary'),remote_trial_path=remote)
    if remote==EXCLUDED or rid=='tag_20260909_173746_028090':
        r.update(disposition='excluded_by_user',reason='Uphill insufficient torque/sliding; excluded from all numerical aggregates and windows');reports.append(r);continue
    rows=[]
    if (p/'camera/frames.csv').exists():
        with (p/'camera/frames.csv').open() as f:rows=list(csv.DictReader(f))
    gt=np.array([[float(x['t']),float(x['s_m'])] for x in rows if x.get('valid')=='1' and x.get('s_m') not in (None,'')]).reshape(-1,2)
    r['camera']=dict(frames=len(rows),valid=len(gt),reasons=dict(Counter(x.get('reason') for x in rows)),forward_axis=capture.get('forward_axis','y_legacy'),timestamp_offset_s=capture.get('time_offset_s'),verified_for_training=capture.get('verified_for_training',False))
    if len(gt)>1:r['camera']['timing']=timing(gt)
    bags=list(p.glob('**/bag/metadata.yaml'))
    if not bags:
        r['disposition']='camera_only' if rows else 'no_measurements'
        r['recover_remote_bag']=remote is not None
        reports.append(r);continue
    try:streams,counts=bagdata(bags[0].parent)
    except Exception as e:r.update(disposition='bag_read_error',error=str(e));reports.append(r);continue
    r['topic_counts']=counts;r['sensor_timing']={k:timing(v) for k,v in streams.items() if len(v)>1}
    if '/wheel/odom' not in streams or '/imu' not in streams:
        r['disposition']='command_only_or_incomplete';reports.append(r);continue
    w=streams['/wheel/odom'];imu=streams['/imu'];wd=np.r_[0,np.cumsum(np.diff(w[:,0])*w[1:,1])]
    r.update(disposition='sensor_diagnostics',wheel_distance_m=float(wd[-1]),duration_s=float(w[-1,0]-w[0,0]),wheel_yaw_deg=float(np.degrees(np.unwrap(w[:,5])[-1]-np.unwrap(w[:,5])[0])),imu_yaw_deg=float(np.degrees(np.trapezoid(imu[:,-1],imu[:,0]))))
    if '/odometry/filtered' in streams:
        ekf=streams['/odometry/filtered'];r['ekf_yaw_deg']=float(np.degrees(np.unwrap(ekf[:,5])[-1]-np.unwrap(ekf[:,5])[0]))
    evpath=bags[0].parent.parent/'command-events.jsonl'
    ev=[json.loads(l) for l in evpath.read_text().splitlines()] if evpath.exists() else []
    durations=Counter()
    for x,y in zip(ev,ev[1:]):durations[x['event']]+=y['monotonic_s']-x['monotonic_s']
    r['command_duration_s']=dict(durations)
    indices=np.interp(imu[:,0],w[:,0],abs(w[:,1]))>.02
    # Differences only within consecutive moving samples; removes static gravity
    # without conflating disjoint motion blocks. Not a calibrated spectral metric.
    adjacent=indices[1:]&indices[:-1]&(np.diff(imu[:,0])<.03)
    for cols,name in [(slice(1,4),'accel_difference_rms'),(slice(4,7),'gyro_difference_rms')]:
        differences=np.diff(imu[:,cols],axis=0)[adjacent]
        r[name]=float(np.sqrt(np.mean(np.sum(differences**2,axis=1)))) if len(differences) else None
    r['imu_moving_samples']=int(sum(indices))
    windows=[];excluded=Counter()
    common=gt[(gt[:,0]>=w[0,0])&(gt[:,0]<=w[-1,0])]
    segments=[]
    if len(common)>1:
        splits=np.r_[0,np.flatnonzero(np.diff(common[:,0])>.2)+1,len(common)]
        for i,j in zip(splits,splits[1:]):
            seg=common[i:j]
            if len(seg)<2:continue
            delta=float(np.interp(seg[-1,0],w[:,0],wd)-np.interp(seg[0,0],w[:,0],wd))
            segments.append(dict(start=float(seg[0,0]),end=float(seg[-1,0]),duration_s=float(seg[-1,0]-seg[0,0]),camera_m=float(seg[-1,1]-seg[0,1]),wheel_m=delta))
        ds=float(common[-1,1]-common[0,1]);de=float(np.interp(common[-1,0],w[:,0],wd)-np.interp(common[0,0],w[:,0],wd))
        r['common']=dict(camera_m=ds,wheel_m=de,ratio=ds/de if abs(de)>.02 else None,interval_s=float(common[-1,0]-common[0,0]),note='Zero-offset camera endpoints; gaps not integrated or used as window labels')
        if capture.get('forward_axis','y')!='x':excluded['legacy_axis_unverified']+=1
        else:
            for end in np.arange(common[0,0]+1,common[-1,0],.05):
                start=end-1
                wi=(w[:,0]>=start)&(w[:,0]<=end)
                im=(imu[:,0]>=start)&(imu[:,0]<=end)
                delta=float(np.interp(end,w[:,0],wd)-np.interp(start,w[:,0],wd))
                if delta<.02:excluded['low_distance']+=1;continue
                if not sum(wi) or np.any(w[wi,1]<-.005):excluded['wheel_reversal']+=1;continue
                lo=max(0,np.searchsorted(common[:,0],start)-1);hi=np.searchsorted(common[:,0],end)
                if np.any(np.diff(common[lo:hi+1,0])>.2):excluded['gt_gap']+=1;continue
                if sum(im)<80 or np.max(np.diff(imu[im,0]))>.05:excluded['imu_gap_or_rate']+=1;continue
                distance=float(np.interp(end,common[:,0],common[:,1])-np.interp(start,common[:,0],common[:,1]))
                features=[float(np.linalg.norm(np.std(imu[im,1:4],axis=0))),float(np.linalg.norm(np.std(imu[im,4:7],axis=0)))]
                windows.append([rid,r['terrain'],float(end),distance,delta,distance/delta,*features])
    r['segments']=segments;r['continuous_gt_seconds']=sum(s['duration_s'] for s in segments)
    r['candidate_windows']=len(windows);r['window_exclusions']=dict(excluded);r['window_ratio']=quant([x[5] for x in windows])
    if windows:r['disposition']='paired_candidate_unvalidated'
    all_windows.extend(windows)
    # Keep the measured camera gaps visible; never draw an implied path across them.
    fig,axes=plt.subplots(3,1,figsize=(9,7),sharex=True)
    t0=w[0,0];axes[0].plot(w[:,0]-t0,wd,label='encoder integral',lw=1.5)
    if len(common):axes[0].scatter(common[:,0]-t0,common[:,1]-common[0,1],s=3,label='camera (zero-offset)')
    axes[0].set_ylabel('distance (m)');axes[0].legend(loc='upper left');axes[0].set_title(rid+' | '+r['terrain'])
    axes[1].plot(w[:,0]-t0,w[:,1],label='wheel vx',lw=1)
    if '/cmd_vel' in streams:
        cmd=streams['/cmd_vel'];axes[1].step(cmd[:,0]-t0,cmd[:,1],where='post',label='cmd vx',lw=1)
    axes[1].set_ylabel('m/s');axes[1].legend()
    if windows:axes[2].scatter([x[2]-t0 for x in windows],[x[5] for x in windows],s=4)
    axes[2].axhline(1,color='gray',ls='--');axes[2].set_ylabel('camera / wheel\n1s candidate');axes[2].set_xlabel('seconds from first wheel sample')
    for ax in axes:ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(OUT/(short+'_timeseries.png'),dpi=130);plt.close(fig)
    reports.append(r)
    print(short,r['disposition'],'wheel',round(r['wheel_distance_m'],3),'ratio',r.get('common',{}).get('ratio'),'windows',len(windows),flush=True)

(OUT/'runs.json').write_text(json.dumps(reports,indent=2,allow_nan=False))
with (OUT/'candidate_windows_UNVALIDATED.csv').open('w') as f:
    writer=csv.writer(f);writer.writerow(window_fields);writer.writerows(all_windows)
fields=['run_id','terrain','status','disposition','wheel_distance_m','camera_common_m','wheel_common_m','ratio','candidate_windows','accel_difference_rms','wheel_yaw_deg','imu_yaw_deg','ekf_yaw_deg']
with (OUT/'run_summary.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    for r in reports:
        row={k:r.get(k) for k in fields};c=r.get('common',{});row.update(camera_common_m=c.get('camera_m'),wheel_common_m=c.get('wheel_m'),ratio=c.get('ratio'));writer.writerow(row)
summary=dict(runs=len(reports),dispositions=dict(Counter(r['disposition'] for r in reports)),candidate_windows=len(all_windows),excluded_remote_path=EXCLUDED,training_approved=False)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
