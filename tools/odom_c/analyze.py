"""Feature/label exploration followed by simple run-disjoint Ridge diagnostics."""
import argparse,json,csv
from pathlib import Path
import numpy as np
from scipy.stats import pearsonr,spearmanr,rankdata
from pipeline import CORE,STATE,write_csv

def read(p):
 with p.open() as f:return list(csv.DictReader(f))
def number(r,k):return float(r[k])
def corr(x,y,rank=False):
 return float((spearmanr if rank else pearsonr)(x,y).statistic) if len(x)>=4 and np.ptp(x)>1e-12 and np.ptp(y)>1e-12 else None
def partial(x,y,speed,rank=False):
 if rank:x,y,speed=rankdata(x),rankdata(y),rankdata(speed)
 A=np.column_stack([np.ones(len(x)),speed]);xr=x-A@np.linalg.lstsq(A,x,rcond=None)[0];yr=y-A@np.linalg.lstsq(A,y,rcond=None)[0]
 return corr(xr,yr)
def relationships(rows,features):
 result=[]
 groups={'all':rows}
 for bin in sorted({r['speed_bin'] for r in rows}):groups['speed_bin:'+bin]=[r for r in rows if r['speed_bin']==bin]
 for terrain in sorted({r['terrain_id'] for r in rows}-{'unknown','mixed'}):
  groups['terrain:'+terrain]=[r for r in rows if r['terrain_id']==terrain]
  for bin in sorted({r['speed_bin'] for r in rows}):groups['terrain_speed:'+terrain+':'+bin]=[r for r in rows if r['terrain_id']==terrain and r['speed_bin']==bin]
 for group,rr in groups.items():
  if len(rr)<4:continue
  y=np.array([number(r,'C_GT') for r in rr]);v=np.array([number(r,'vx_mean') for r in rr])
  for f in features:
   x=np.array([number(r,f) for r in rr]);result.append(dict(group=group,feature=f,n_windows=len(rr),n_runs=len({r['run_id'] for r in rr}),pearson=corr(x,y),spearman=corr(x,y,True),speed_partial_pearson=partial(x,y,v),speed_partial_rank=partial(x,y,v,True)))
 return result

def fit(train,features,alpha):
 X=np.array([[number(r,f) for f in features] for r in train]);y=np.array([number(r,'C_GT') for r in train]);counts={i:sum(r['run_id']==i for r in train) for i in {r['run_id'] for r in train}};weights=np.array([1/counts[r['run_id']] for r in train]);weights*=len(train)/weights.sum()
 mean=np.average(X,axis=0,weights=weights);scale=np.sqrt(np.average((X-mean)**2,axis=0,weights=weights));scale=np.maximum(scale,1e-9);intercept=float(np.average(y,weights=weights));Z=(X-mean)/scale
 beta=np.linalg.solve(Z.T@(weights[:,None]*Z)+alpha*np.eye(len(features)),Z.T@(weights*(y-intercept)))
 return dict(features=features,alpha=alpha,mean=mean.tolist(),scale=scale.tolist(),beta=beta.tolist(),intercept=intercept)
def predict(model,rows):
 X=np.array([[number(r,f) for f in model['features']] for r in rows]);return model['intercept']+(X-np.array(model['mean']))/np.array(model['scale'])@np.array(model['beta'])
def mae(model,rr):return float(np.mean(abs(predict(model,rr)-np.array([number(r,'C_GT') for r in rr]))))
def disjoint(rows):
 keep=[];last={}
 for r in sorted(rows,key=lambda r:(r['run_id'],number(r,'timestamp_start'))):
  if number(r,'timestamp_start')>=last.get(r['run_id'],-np.inf)-1e-6:keep.append(r);last[r['run_id']]=number(r,'timestamp_end')
 return keep

def distance_metrics(rows,pred):
 for r,p in zip(rows,pred):r['_pred']=float(p)
 metrics=[];traces=[]
 for run in sorted({r['run_id'] for r in rows}):
  rr=disjoint([r for r in rows if r['run_id']==run]);enc=np.array([number(r,'Delta_s_encoder') for r in rr]);gt=np.array([number(r,'Delta_s_GT') for r in rr]);pp=np.array([r['_pred'] for r in rr]);cc=np.array([number(r,'C_GT') for r in rr]);corrected=enc*pp
  no=abs(cc-1)<=.03;slip=cc<.95;err=enc-gt;cerr=corrected-gt
  metrics.append(dict(run_id=run,nonoverlap_windows=len(rr),covered_seconds=sum(number(r,'window_s') for r in rr),GT_distance_m=float(gt.sum()),encoder_distance_m=float(enc.sum()),corrected_distance_m=float(corrected.sum()),encoder_final_error_m=float(err.sum()),corrected_final_error_m=float(cerr.sum()),encoder_relative_error=float(err.sum()/gt.sum()) if abs(gt.sum())>1e-9 else None,corrected_relative_error=float(cerr.sum()/gt.sum()) if abs(gt.sum())>1e-9 else None,encoder_sum_absolute_interval_error_m=float(abs(err).sum()),corrected_sum_absolute_interval_error_m=float(abs(cerr).sum()),C_RMSE=float(np.sqrt(np.mean((pp-cc)**2))),no_slip_pred_bias=float((pp[no]-1).mean()) if no.any() else None,no_slip_n=int(no.sum()),slip_n=int(slip.sum()),slip_error_improvement_m=float(abs(err[slip]).sum()-abs(cerr[slip]).sum()) if slip.any() else None,full_run_final_distance_error=None,scope='sum of disjoint quality-valid intervals only; gaps not bridged, not full-run final distance'))
  for k,r in enumerate(rr):traces.append(dict(run_id=run,timestamp_end=r['timestamp_end'],C_GT=r['C_GT'],C_pred=pp[k],encoder_accumulated_m=float(enc[:k+1].sum()),corrected_accumulated_m=float(corrected[:k+1].sum()),GT_accumulated_m=float(gt[:k+1].sum())))
 return metrics,traces

def main():
 p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);a=p.parse_args();out=a.dataset
 rows=read(out/'windows.csv');features=list(dict.fromkeys(CORE['raw']+CORE['detrended']));rel=relationships(rows,features);write_csv(out/'feature_correlations.csv',rel)
 ids=sorted({r['run_id'] for r in rows});n=len(ids)
 summary=dict(n_windows=len(rows),n_runs=n,terrain_control_available=all(r['terrain_id'] not in ['unknown','mixed'] for r in rows),terrain_control_note='Unlabelled windows are not treated as one terrain.',PSD_cutoff='No cutoff chosen; compare raw statistics with linear-detrended residuals. PSD cannot identify terrain/body causes by itself.',regression_status='not_run',acceptance='not_established')
 if n<5:
  summary['regression_status']='insufficient_runs_for_train_validation_test';(out/'analysis.json').write_text(json.dumps(summary,indent=2));return
 # Freeze before model scoring. No random window split.
 test_ids=ids[-max(1,n//5):];val_ids=ids[-2*max(1,n//5):-max(1,n//5)];train_ids=[i for i in ids if i not in val_ids+test_ids]
 train=[r for r in rows if r['run_id'] in train_ids];val=[r for r in rows if r['run_id'] in val_ids];test=[r for r in rows if r['run_id'] in test_ids]
 split=dict(train=train_ids,validation=val_ids,test=test_ids);(out/'split.json').write_text(json.dumps(split,indent=2))
 train_rel=relationships(train,features);write_csv(out/'training_feature_correlations.csv',train_rel)
 # A permissive exploratory gate, not proof of physical slip sensitivity.
 candidates=[r for r in train_rel if r['group']=='all' and r['feature'].startswith(('raw_','detrended_')) and r['speed_partial_rank'] is not None and abs(r['speed_partial_rank'])>=.3]
 summary['training_relationship_gate']=dict(status='exploratory_candidates_present' if candidates else 'no_candidates',rule='training-only |speed-partial rank correlation| >=0.3; not statistical confirmation',candidates=candidates)
 if not candidates:
  summary['regression_status']='withheld_no_training_relationship';summary['split']=split
  mm,tt=distance_metrics([dict(r) for r in test],np.ones(len(test)))
  summary['encoder_only_test_audit']=mm
  write_csv(out/'encoder_only_test.csv',mm);write_csv(out/'encoder_only_trace.csv',tt)
  (out/'ridge_status.json').write_text(json.dumps(dict(status='not_trained',reason='No prespecified IMU candidate exceeds the declared training-only speed-controlled screening threshold. Do not train by inspecting test outcomes.',implemented_models=list(CORE),holdout=split),indent=2))
  write_csv(out/'runwise_holdout_status.csv',[dict(run_id=i,split=part,status='model_withheld',corrected_error_m='unavailable') for part,group in split.items() for i in group])
  (out/'analysis.json').write_text(json.dumps(summary,indent=2));return
 specs={'encoder_only':STATE,**CORE};alphas=[.1,1.,10.,100.];scores=[];models={}
 for mode,cols in specs.items():
  options=[]
  for alpha in alphas:
   m=fit(train,cols,alpha);loss=mae(m,val);options.append((loss,alpha,m));scores.append(dict(mode=mode,alpha=alpha,validation_C_MAE=loss))
  loss,alpha,model=min(options,key=lambda r:r[0]);models[mode]=model
 chosen=min(models,key=lambda mode:mae(models[mode],val));selected=models[chosen]
 predrows=[];metrics=[];traces=[]
 # Report the frozen test once; additional models are explicit ablations, not test-selected.
 for name,model in models.items():
  pp=predict(model,test);mm,tt=distance_metrics([dict(r) for r in test],pp)
  metrics.extend(dict(model=name,selected=name==chosen,**r) for r in mm);traces.extend(dict(model=name,**r) for r in tt)
  predrows.extend(dict(model=name,run_id=r['run_id'],timestamp_start=r['timestamp_start'],timestamp_end=r['timestamp_end'],C_GT=r['C_GT'],C_pred=float(v)) for r,v in zip(test,pp))
 train_mean=float(np.mean([number(r,'C_GT') for r in train]))
 for name,value in [('C_equals_1',1.),('training_constant',train_mean)]:
  mm,tt=distance_metrics([dict(r) for r in test],np.full(len(test),value));metrics.extend(dict(model=name,selected=False,**r) for r in mm);traces.extend(dict(model=name,**r) for r in tt)
 # Nested leave-one-run-out diagnostic: held-out run never used for scaling/tuning.
 loro=[]
 for held in ids:
  pool=[r for r in rows if r['run_id']!=held];test_run=[r for r in rows if r['run_id']==held];choices=[]
  for mode,cols in specs.items():
   for alpha in alphas:
    losses=[]
    for inner in [i for i in ids if i!=held]:
     it=[r for r in pool if r['run_id']!=inner];iv=[r for r in pool if r['run_id']==inner];losses.append(mae(fit(it,cols,alpha),iv))
    choices.append((float(np.mean(losses)),mode,alpha))
  _,mode,alpha=min(choices);m=fit(pool,specs[mode],alpha);mm,_=distance_metrics([dict(r) for r in test_run],predict(m,test_run));loro.extend(dict(selected_mode=mode,alpha=alpha,**r) for r in mm)
 write_csv(out/'ridge_validation.csv',scores);write_csv(out/'test_predictions.csv',predrows);write_csv(out/'test_odometry.csv',metrics);write_csv(out/'distance_traces.csv',traces);write_csv(out/'leave_one_run_out.csv',loro)
 (out/'ridge_models.json').write_text(json.dumps(models,indent=2))
 summary.update(regression_status='exploratory_ridge_diagnostic_only',split=split,selected_on_validation=chosen,test_metrics=metrics,leave_one_run_out=loro,training_constant_C=train_mean,acceptance='not_established: terrain unknown, exposure delay uncalibrated, sparse independent runs and incomplete full-run GT coverage',conclusion='No A/B/C/D category can yet be established conclusively. Inspect unseen-run errors for evidence of D; do not claim A from training/window correlations.')
 (out/'analysis.json').write_text(json.dumps(summary,indent=2));print('Selected',chosen,'test metrics',json.dumps([r for r in metrics if r['selected']],indent=2));print('LORO',[(r['run_id'],r['encoder_final_error_m'],r['corrected_final_error_m']) for r in loro])
if __name__=='__main__':main()
