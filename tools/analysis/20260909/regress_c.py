"""Exploratory C regression: nested whole-bag holdouts; no terrain labels."""
from pathlib import Path
import csv,json
import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
import classify

OUT=Path(__file__).resolve().parents[3]/'data/apriltag_gt/analysis_20260909/classification/regression'
ROOT=OUT.parents[2]
ALPHAS=[1.,10.,100.,1000.]

def paired(raw,shift):
    runs=[]
    for r in raw:
        base=ROOT/r['id']; cap=base/'camera/capture.json'; frames=base/'camera/frames.csv'
        if not cap.exists() or not frames.exists():continue
        if json.loads(cap.read_text()).get('forward_axis')!='x':continue
        with frames.open() as f:
            gt=np.array([[float(x['t'])+shift,float(x['s_m'])] for x in csv.DictReader(f) if x['valid']=='1' and x['s_m']])
        if len(gt)<2 or np.any(np.diff(gt[:,0])<=0):continue
        path=next(base.glob('**/bag/metadata.yaml')).parent; w=[]
        with AnyReader([path],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
            for c,t,data in bag.messages(connections=[c for c in bag.connections if c.topic=='/wheel/odom']):
                m=bag.deserialize(data,c.msgtype);w.append([m.header.stamp.sec+m.header.stamp.nanosec/1e9,m.twist.twist.linear.x])
        w=np.array(w);dist=np.r_[0,np.cumsum(np.diff(w[:,0])*(w[1:,1]+w[:-1,1])/2)]
        items=[];last=-np.inf
        for x,end in zip(r['X'],r['end']):
            start=end-1
            if start<last-1e-6 or start<gt[0,0] or end>gt[-1,0]:continue
            lo=np.searchsorted(gt[:,0],start,side='right')-1;hi=np.searchsorted(gt[:,0],end)
            if max(np.diff(gt[lo:hi+1,0]),default=0)>.2:continue
            wd=np.interp(end,w[:,0],dist)-np.interp(start,w[:,0],dist)
            if wd<.02:continue
            gd=np.interp(end,gt[:,0],gt[:,1])-np.interp(start,gt[:,0],gt[:,1])
            items.append((x,gd/wd,wd,gd,start,end));last=end
        if items:runs.append(dict(id=r['id'],X=np.array([i[0] for i in items]),y=np.array([i[1] for i in items]),w=np.array([i[2] for i in items]),g=np.array([i[3] for i in items]),times=np.array([i[4:] for i in items])))
    return runs

def predict(train,test,cols,alpha):
    X=np.vstack([r['X'][:,cols] for r in train]);y=np.concatenate([r['y'] for r in train])
    weights=np.concatenate([np.full(len(r['y']),1/len(r['y'])) for r in train]);weights/=weights.sum()
    mean=np.average(X,axis=0,weights=weights);scale=np.sqrt(np.maximum(np.average((X-mean)**2,axis=0,weights=weights),1e-12))
    z=(X-mean)/scale;intercept=np.average(y,weights=weights)
    # Alpha expressed on a per-bag-equivalent sample scale.
    weights*=len(train)
    beta=np.linalg.solve(z.T@(weights[:,None]*z)+alpha*np.eye(len(cols)),z.T@(weights*(y-intercept)))
    return intercept+(test['X'][:,cols]-mean)/scale@beta

def evaluate(runs):
    groups={'imu':list(range(48)),'wheel':list(range(48,56)),'combined':list(range(56))}; rows=[];predictions=[]
    for i,test in enumerate(runs):
        train=[r for j,r in enumerate(runs) if j!=i]
        fixed=np.mean([r['g'].sum()/r['w'].sum() for r in train])
        preds={'raw':np.ones(len(test['y'])),'constant':np.full(len(test['y']),fixed)};chosen={}
        for name,cols in groups.items():
            scores=[]
            for alpha in ALPHAS:
                scores.append(np.mean([np.mean(abs((predict([r for k,r in enumerate(train) if k!=j],v,cols,alpha)-v['y'])*v['w'])) for j,v in enumerate(train)]))
            alpha=ALPHAS[int(np.argmin(scores))];chosen[name]=dict(alpha=alpha,validation_mae_m=float(min(scores)))
            preds[name]=predict(train,test,cols,alpha)
        row=dict(run_id=test['id'],windows=len(test['y']),camera_m=float(test['g'].sum()),wheel_m=float(test['w'].sum()),true_C=float(test['g'].sum()/test['w'].sum()),selected=chosen,metrics={})
        for name,p in preds.items():
            e=p*test['w']-test['g']
            row['metrics'][name]=dict(window_mae_m=float(np.mean(abs(e))),C_mae=float(np.mean(abs(p-test['y']))),signed_total_error_m=float(e.sum()),absolute_total_error_m=float(abs(e.sum())),predicted_C_min=float(p.min()),predicted_C_max=float(p.max()))
            for j in range(len(p)):predictions.append(dict(run_id=test['id'],model=name,start=test['times'][j,0],end=test['times'][j,1],camera_m=test['g'][j],wheel_m=test['w'][j],true_C=test['y'][j],predicted_C=p[j]))
        rows.append(row)
    summary={name:{metric:float(np.mean([r['metrics'][name][metric] for r in rows])) for metric in ['window_mae_m','C_mae','absolute_total_error_m']} for name in ['raw','constant',*groups]}
    return dict(bags=len(runs),windows=sum(len(r['y']) for r in runs),summary=summary,details=rows),predictions

def main():
    OUT.mkdir(exist_ok=True)
    raw,_=classify.extract()
    all_results={}
    for shift in [0.,-.1,.1]:
        runs=paired(raw,shift)
        if shift==0:
            ids={r['id'] for r in runs}
        else:runs=[r for r in runs if r['id'] in ids]
        result,preds=evaluate(runs);all_results[str(shift)]=result
        print('SHIFT',shift,json.dumps(result['summary']),flush=True)
        if shift==0:
            with (OUT/'heldout_predictions.csv').open('w') as f:
                writer=csv.DictWriter(f,fieldnames=list(preds[0]));writer.writeheader();writer.writerows(preds)
    (OUT/'results.json').write_text(json.dumps(all_results,indent=2))
    (OUT/'method.txt').write_text('No terrain labels. Nested leave-one-bag-out: outer test unseen in scaling, ridge fitting and alpha selection; inner whole-bag validation minimizes mean per-bag window distance MAE. Fixed alphas 1,10,100,1000. 1s nonoverlapping accepted windows, no bridging GT gaps >0.2s, wheel travel >=0.02m. No C clipping or outcome-based rejection. Constant C is mean training-bag camera/wheel ratio. Test metrics refer only to accepted windows, not entire drives. Camera GT unverified for exposure delay; shifts +/-0.1s are sensitivity checks, not fitted corrections. No runtime deployment.\n')

if __name__=='__main__':main()
