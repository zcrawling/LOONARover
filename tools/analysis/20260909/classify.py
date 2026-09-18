"""Whole-bag holdout terrain separability, without camera labels or temporal leakage."""
from pathlib import Path
import json
from collections import Counter
import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import get_typestore,Stores

OUT=Path(__file__).resolve().parents[3]/'data/apriltag_gt/analysis_20260909/classification'
ROOT=OUT.parents[1]

def extract():
    inventory=json.loads((OUT.parent/'runs.json').read_text());runs=[];notes=[]
    names=[]
    for entry in inventory:
        if entry['disposition']=='excluded_by_user':continue
        paths=list((ROOT/entry['run_id']).glob('**/bag/metadata.yaml'))
        if not paths:continue
        imu=[];wheel=[]
        with AnyReader([paths[0].parent],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
            for c,t,raw in bag.messages(connections=[c for c in bag.connections if c.topic in ['/imu','/wheel/odom']]):
                if c.topic not in ['/imu','/wheel/odom']:continue
                m=bag.deserialize(raw,c.msgtype);t=m.header.stamp.sec+m.header.stamp.nanosec/1e9
                if c.topic=='/imu':imu.append([t,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
                else:wheel.append([t,m.twist.twist.linear.x,m.twist.twist.angular.z])
        if len(imu)<100 or len(wheel)<50:continue
        imu=np.array(imu);wheel=np.array(wheel);features=[];ends=[]
        for end in np.arange(max(imu[0,0],wheel[0,0])+1,min(imu[-1,0],wheel[-1,0]),.5):
            start=end-1;im=imu[(imu[:,0]>=start)&(imu[:,0]<=end)];w=wheel[(wheel[:,0]>=start)&(wheel[:,0]<=end)]
            if len(im)<80 or len(w)<35 or max(np.diff(im[:,0]))>.05 or max(np.diff(w[:,0]))>.05:continue
            if np.mean(w[:,1]>.02)<.8:continue
            grid=np.linspace(start,end,100,endpoint=False)
            signals=np.column_stack([np.interp(grid,imu[:,0],imu[:,j]) for j in range(1,7)])
            f=[];names=[]
            for j,axis in enumerate(['ax','ay','az','gx','gy','gz']):
                a=signals[:,j];z=a-a.mean();std=np.std(z)
                power=abs(np.fft.rfft(z*np.hanning(len(z))))**2;freq=np.fft.rfftfreq(len(z),.01)
                stats=dict(std=std,diff_rms=np.sqrt(np.mean(np.diff(z)**2)),mad=np.median(abs(z-np.median(z))),ptp=np.ptp(z),kurt=np.mean(z**4)/max(std**4,1e-16),low=np.sum(power[(freq>=2)&(freq<10)]),mid=np.sum(power[(freq>=10)&(freq<25)]),high=np.sum(power[(freq>=25)&(freq<=45)]))
                for key,value in stats.items():names.append(axis+'_'+key);f.append(float(value))
            for j,axis in [(1,'vx'),(2,'wz')]:
                a=w[:,j]
                for key,value in dict(mean=a.mean(),std=a.std(),ptp=np.ptp(a),diff_rms=np.sqrt(np.mean(np.diff(a)**2))).items():names.append(axis+'_'+key);f.append(float(value))
            if not np.isfinite(f).all():continue
            features.append(f);ends.append(end)
        notes.append(dict(run_id=entry['run_id'],terrain=entry['terrain'],windows=len(features)))
        if features:runs.append(dict(id=entry['run_id'],label=entry['terrain'],X=np.array(features),end=ends))
        print(entry['short'],entry['terrain'],len(features),flush=True)
    (OUT/'extraction.json').write_text(json.dumps(dict(runs=notes,features=names,window_s=1,stride_s=.5,moving_fraction_min=.8),indent=2))
    return runs,names

def evaluate(runs,cols,labels=None):
    labels=np.array(labels if labels is not None else [r['label'] for r in runs]);classes=sorted(set(labels));cm=np.zeros((len(classes),len(classes)),int);details=[]
    # One vector per training bag for the centroid; longer bags get no extra weight.
    for i,test in enumerate(runs):
        train=[j for j in range(len(runs)) if j!=i]
        assert i not in train
        mean=np.mean([runs[j]['X'][:,cols].mean(axis=0) for j in train],axis=0)
        var=np.mean([np.mean((runs[j]['X'][:,cols]-mean)**2,axis=0) for j in train],axis=0)
        scale=np.sqrt(np.maximum(var,1e-12))
        centres=np.array([np.mean([(runs[j]['X'][:,cols].mean(axis=0)-mean)/scale for j in train if labels[j]==c],axis=0) for c in classes])
        z=(test['X'][:,cols]-mean)/scale
        distance=np.mean((z[:,None,:]-centres[None,:,:])**2,axis=2)
        predictions=np.argmin(distance,axis=1)
        votes=np.bincount(predictions,minlength=len(classes))
        best=np.flatnonzero(votes==max(votes));guess=int(best[np.argmin(distance.mean(axis=0)[best])])
        actual=classes.index(labels[i]);cm[actual,guess]+=1
        details.append(dict(run_id=test['id'],actual=str(labels[i]),predicted=classes[guess],windows=len(z),window_accuracy=float(np.mean(predictions==actual)),votes=votes.tolist()))
    recalls=np.diag(cm)/cm.sum(axis=1)
    return dict(classes=classes,confusion=cm.tolist(),bag_accuracy=float(np.trace(cm)/cm.sum()),balanced_bag_accuracy=float(np.mean(recalls)),balanced_window_accuracy=float(np.mean([np.mean([d['window_accuracy'] for d in details if d['actual']==c]) for c in classes])),details=details)

def main():
    runs,names=extract();counts=Counter(r['label'] for r in runs)
    eligible=[r for r in runs if counts[r['label']]>=2]
    groups={'imu_vibration':list(range(48)),'wheel_only':list(range(48,56)),'combined':list(range(56))}
    result=dict(method='fixed standardized nearest class centroid, per-bag equal weight, leave-one-whole-bag-out; no parameter search',included_runs=[dict(run_id=r['id'],terrain=r['label'],windows=len(r['X'])) for r in eligible],omitted_singleton_classes=[k for k,v in counts.items() if v<2],camera_used=False,uphill_excluded=True)
    rng=np.random.default_rng(20260909)
    permutations=[rng.permutation([r['label'] for r in eligible]).tolist() for _ in range(199)]
    for name,cols in groups.items():
        score=evaluate(eligible,cols)
        null=np.array([evaluate(eligible,cols,labels)['balanced_bag_accuracy'] for labels in permutations])
        score.update(permutation_p=float((1+sum(null>=score['balanced_bag_accuracy']))/200),null_p95=float(np.quantile(null,.95)),permutation_count=199)
        result[name]=score
        print(name,score['bag_accuracy'],score['balanced_bag_accuracy'],score['balanced_window_accuracy'],'p',score['permutation_p'],flush=True)
    # Sensitivity: short bursts omitted, no retuning of the classifier.
    stable=[r for r in eligible if len(r['X'])>=5];ct=Counter(r['label'] for r in stable);stable=[r for r in stable if ct[r['label']]>=2]
    result['at_least_five_windows']=dict(runs=[r['id'] for r in stable],scores={n:evaluate(stable,c) for n,c in groups.items()}) if len(set(r['label'] for r in stable))>=2 else None
    # Coarser labels cannot be selected post hoc as the primary result.
    coarse=[dict(r,label='hard_outdoor' if r['label'] in ['stone_asphalt','rough_paving'] else r['label']) for r in eligible]
    result['coarse_exploratory']={n:evaluate(coarse,c) for n,c in groups.items()}
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    np.savez_compressed(OUT/'window_features.npz',X=np.vstack([r['X'] for r in runs]),run_id=np.concatenate([[r['id']]*len(r['X']) for r in runs]),terrain=np.concatenate([[r['label']]*len(r['X']) for r in runs]),feature_names=names)

if __name__=='__main__':main()
