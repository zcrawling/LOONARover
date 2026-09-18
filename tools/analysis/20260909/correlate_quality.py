"""Quality-filtered exploratory feature/C correlations, grouped by recorded run."""
from pathlib import Path
import csv,json,sys
from collections import Counter
import numpy as np
from scipy.stats import spearmanr,pearsonr,rankdata
from rosbags.highlevel import AnyReader
from rosbags.typesys import get_typestore,Stores

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/apriltag_gt'))
from loonar_apriltag.trial_analysis import motion_intervals
OUT=ROOT/'data/apriltag_gt/analysis_20260909/quality_correlations'
CONFIG=dict(window_s=3.,settle_s=2.,stop_guard_s=.5,tag_fraction_min=.95,tag_max_gap_s=.25,reprojection_max_px=1.,heading_max_deg=3.,camera_fit_rms_max_m=.002,wheel_std_max_mps=.003,wheel_min_mps=.035,imu_gap_max_s=.025,wheel_gap_max_s=.05,C_shift_range_max=.04,shift_s=[-.1,0,.1])
SCREENED='--screened' in sys.argv
if SCREENED:
    OUT=OUT/'screened'
    CONFIG.update(tag_fraction_min=.9,tag_max_gap_s=.3,reprojection_max_px=1.5,heading_max_deg=10.,camera_fit_rms_max_m=.003,wheel_std_max_mps=.005,wheel_min_mps=.035,wheel_steadiness='0.5s block means',heading_change_within_window_max_deg=2.)

def slope(t,x):
    t=t-t.mean();return float(t@(x-x.mean())/(t@t))

def features(im,w):
    # Band power: one-sided periodogram, variance units, mean and Hann window.
    signals=np.column_stack([np.interp(np.arange(300)/100+im[0,0],im[:,0],im[:,j]) for j in range(1,7)])
    f={}
    for a,x in zip(['ax','ay','az','gx','gy','gz'],signals.T):
        z=x-x.mean();std=z.std();h=np.hanning(len(z));power=abs(np.fft.rfft(z*h))**2/(100*np.sum(h*h));power[1:-1]*=2;freq=np.fft.rfftfreq(len(z),.01)
        stats=dict(std=std,diff_rms=np.sqrt(np.mean(np.diff(z)**2)),mad=np.median(abs(z-np.median(z))),ptp=np.ptp(z),kurt=np.mean(z**4)/max(std**4,1e-16))
        for low,high in [(2,10),(10,25),(25,45)]:stats[f'power_{low}_{high}']=np.sum(power[(freq>=low)&(freq<high)])*(100/len(z))
        f.update({a+'_'+k:float(v) for k,v in stats.items()})
    for a,x in zip(['vx','wz'],w[:,1:].T):
        f.update({a+'_'+k:float(v) for k,v in dict(mean=x.mean(),std=x.std(),ptp=np.ptp(x),diff_rms=np.sqrt(np.mean(np.diff(x)**2))).items()})
    return f

def extract():
    accepted=[];audit=[]
    for p in sorted((ROOT/'data/apriltag_gt').glob('tag_*')):
        note=dict(run_id=p.name,rejected={});counts=Counter();audit.append(note)
        if p.name=='tag_20260909_173746_028090':note['status']='user_excluded';continue
        paths=list(p.glob('**/bag/metadata.yaml'));cap=p/'camera/capture.json';frames=p/'camera/frames.csv'
        if not paths or not cap.exists() or not frames.exists():note['status']='missing_bag_or_camera';continue
        meta=json.loads(cap.read_text())
        if meta.get('forward_axis')!='x':note['status']='unverified_axis';continue
        ev=paths[0].parent.parent/'command-events.jsonl'
        if not ev.exists():note['status']='missing_motion_events';continue
        intervals=motion_intervals([json.loads(l) for l in ev.read_text().splitlines()],CONFIG['settle_s'],CONFIG['stop_guard_s'])
        imu=[];wheel=[]
        with AnyReader([paths[0].parent],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
            for c,t,b in bag.messages(connections=[c for c in bag.connections if c.topic in ['/imu','/wheel/odom']]):
                if c.topic not in ['/imu','/wheel/odom']:continue
                m=bag.deserialize(b,c.msgtype);t=m.header.stamp.sec+m.header.stamp.nanosec/1e9
                if c.topic=='/imu':imu.append([t,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
                else:wheel.append([t,m.twist.twist.linear.x,m.twist.twist.angular.z])
        if len(imu)<2 or len(wheel)<2:note['status']='missing_sensors';continue
        im=np.array(imu);w=np.array(wheel)
        with frames.open() as file:fr=list(csv.DictReader(file))
        good=[r for r in fr if r['valid']=='1' and r['s_m']]
        gt=np.array([[float(r[k]) for k in ['t','s_m','reprojection_px','heading_change_deg']] for r in good])
        if len(gt)<2:note['status']='missing_valid_tag';continue
        if any(np.any(np.diff(x[:,0])<=0) for x in [gt,im,w]):note['status']='nonmonotonic_time';continue
        wd=np.r_[0,np.cumsum(np.diff(w[:,0])*(w[1:,1]+w[:-1,1])/2)]
        for left,right in intervals:
            last_accepted_end=-np.inf
            for a in np.arange(left,right-3+1e-6,.5):
                if a<last_accepted_end:continue
                b=a+3;g=gt[(gt[:,0]>=a)&(gt[:,0]<=b)];ii=im[(im[:,0]>=a)&(im[:,0]<=b)];ww=w[(w[:,0]>=a)&(w[:,0]<=b)]
                def reject(reason):counts.update([reason])
                n=sum(a<=float(r['t'])<=b for r in fr)
                if len(g)<(12 if SCREENED else 20) or len(g)/max(n,1)<CONFIG['tag_fraction_min']:reject('tag_count_or_fraction');continue
                if max(np.diff(np.r_[a,g[:,0],b]))>CONFIG['tag_max_gap_s']:reject('tag_gap');continue
                if g[:,2].max()>CONFIG['reprojection_max_px'] or abs(g[:,3]).max()>CONFIG['heading_max_deg'] or (SCREENED and np.ptp(g[:,3])>2):reject('pose_quality');continue
                if len(ii)<270 or max(np.diff(np.r_[a,ii[:,0],b]))>.025:reject('imu_timing');continue
                if len(ww)<120 or max(np.diff(np.r_[a,ww[:,0],b]))>.05:reject('wheel_timing');continue
                velocity=np.array([ww[(ww[:,0]>=start)&(ww[:,0]<start+.5),1].mean() for start in np.arange(a,b,.5)]) if SCREENED else ww[:,1]
                if not np.isfinite(velocity).all() or velocity.std()>CONFIG['wheel_std_max_mps'] or velocity.min()<CONFIG['wheel_min_mps']:reject('not_steady');continue
                cam=slope(g[:,0],g[:,1]);res=float(np.sqrt(np.mean((g[:,1]-g[:,1].mean()-cam*(g[:,0]-g[:,0].mean()))**2)))
                if res>CONFIG['camera_fit_rms_max_m']:reject('camera_fit_residual');continue
                cs=[]
                for shift in CONFIG['shift_s']:
                    times=g[:,0]+shift
                    if times[0]<w[0,0] or times[-1]>w[-1,0]:break
                    ws=slope(times,np.interp(times,w[:,0],wd));cs.append(cam/ws if ws>0 else np.nan)
                if len(cs)!=3 or not np.isfinite(cs).all() or np.ptp(cs)>.04:reject('time_shift_sensitive');continue
                accepted.append(dict(run_id=p.name,start=a,end=b,C=cs[1],C_minus=cs[0],C_plus=cs[2],camera_fit_rms_m=res,tag_samples=len(g),**features(ii,ww)))
                last_accepted_end=b
        note.update(status='reviewed',accepted=sum(r['run_id']==p.name for r in accepted),rejected=dict(counts))
        print(p.name,note.get('accepted'),dict(counts),flush=True)
    return accepted,audit

def corr(x,y):
    return float(spearmanr(x,y).statistic) if np.ptp(x)>0 and np.ptp(y)>0 else 0.

def main():
    OUT.mkdir(exist_ok=True);rows,audit=extract()
    (OUT/'selection.json').write_text(json.dumps(dict(config=CONFIG,audit=audit),indent=2))
    if not rows:raise SystemExit('No samples pass the declared quality criteria; criteria were not relaxed.')
    with (OUT/'samples.csv').open('w') as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    ids=sorted({r['run_id'] for r in rows});names=list(rows[0])[8:];y=np.array([r['C'] for r in rows]);group=np.array([ids.index(r['run_id']) for r in rows]);means=np.array([y[group==i].mean() for i in range(len(ids))]);results=[]
    if len(ids)<4:
        report=dict(status='insufficient_independent_bags',samples=len(rows),bags=len(ids),features=len(names),bag_C=[dict(run_id=rid,n=int(sum(group==i)),C=float(means[i])) for i,rid in enumerate(ids)],ranking=[],note='No ranking: two or three independent bags can give misleading near-perfect correlations.')
        (OUT/'correlations.json').write_text(json.dumps(report,indent=2))
        (OUT/'correlations.csv').write_text('feature,pooled_spearman,bag_spearman,fdr_q\n')
        print(json.dumps(report,indent=2));return
    rng=np.random.default_rng(20260909);perms=np.array([rng.permutation(len(ids)) for _ in range(9999)])
    for name in names:
        x=np.array([r[name] for r in rows]);xm=np.array([x[group==i].mean() for i in range(len(ids))]);rho=corr(xm,means)
        if len(ids)>=3 and np.ptp(xm)>0 and np.ptp(means)>0:
            xr=rankdata(xm);yr=rankdata(means);xr-=xr.mean();yr-=yr.mean();null=(yr[perms]@xr)/np.sqrt((xr@xr)*(yr@yr));p=(1+sum(abs(null)>=abs(rho)-1e-12))/10000
        else:p=1.
        leave=[corr(np.delete(xm,i),np.delete(means,i)) for i in range(len(ids))] if len(ids)>3 else []
        within=corr(x-np.array([xm[i] for i in group]),y-np.array([means[i] for i in group]))
        results.append(dict(feature=name,pooled_spearman=corr(x,y),bag_spearman=rho,bag_pearson=float(pearsonr(xm,means).statistic) if np.ptp(xm)>0 and len(ids)>2 else None,within_bag_centered_spearman=within,permutation_p=float(p),leave_one_bag_min=min(leave) if leave else None,leave_one_bag_max=max(leave) if leave else None,shift_minus_bag_rho=corr(xm,np.array([np.mean([r['C_minus'] for r in rows if r['run_id']==rid]) for rid in ids])),shift_plus_bag_rho=corr(xm,np.array([np.mean([r['C_plus'] for r in rows if r['run_id']==rid]) for rid in ids]))))
    order=np.argsort([r['permutation_p'] for r in results]);q=1.
    for rank in range(len(order)-1,-1,-1):
        idx=order[rank];q=min(q,results[idx]['permutation_p']*len(order)/(rank+1));results[idx]['fdr_q']=q
    results.sort(key=lambda r:abs(r['bag_spearman']),reverse=True)
    report=dict(samples=len(rows),bags=len(ids),features=len(names),bag_C=[dict(run_id=rid,n=int(sum(group==i)),C=float(means[i])) for i,rid in enumerate(ids)],ranking=results)
    (OUT/'correlations.json').write_text(json.dumps(report,indent=2))
    with (OUT/'correlations.csv').open('w') as f:
        wr=csv.DictWriter(f,fieldnames=list(results[0]));wr.writeheader();wr.writerows(results)
    print(json.dumps(dict(samples=len(rows),bags=len(ids),top=results[:8]),indent=2),flush=True)

if __name__=='__main__':main()
