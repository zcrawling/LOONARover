"""Direct local-feature versus local-C analysis. No time/run predictors or run averaging."""
from pathlib import Path
import json,csv
import numpy as np
from scipy.stats import spearmanr,pearsonr
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'data/apriltag_gt/analysis_20260910'
def rho(x,y):return float(spearmanr(x,y).statistic) if np.ptp(x)>1e-12 and np.ptp(y)>1e-12 else 0.
def analyze(rows):
 names=sorted(set.intersection(*[set(r['features']) for r in rows]));y=np.array([r['C'] for r in rows]);results=[]
 # Each sample is a paired local measurement. Identity is never a numeric input.
 for name in names:
  x=np.array([r['features'][name] for r in rows]);s=rho(x,y)
  leave=[rho(np.delete(x,i),np.delete(y,i)) for i in range(len(y))]
  distance=np.abs(x[:,None]-x[None,:]);np.fill_diagonal(distance,np.inf)
  # All equally near neighbours count, rather than breaking ties by recording order.
  near=distance==distance.min(axis=1)[:,None];dy=np.abs(y[:,None]-y[None,:])
  nearest=float(np.mean([dy[i,near[i]].mean() for i in range(len(y))]))
  baseline=float(dy[~np.eye(len(y),dtype=bool)].mean())
  results.append(dict(feature=name,spearman=s,pearson=float(pearsonr(x,y).statistic) if np.ptp(x)>1e-12 else 0.,
   leave_one_window_min=min(leave),leave_one_window_max=max(leave),nearest_feature_C_difference=nearest,
   random_other_C_difference=baseline,nearest_improvement=1-nearest/baseline if baseline else 0.))
 results.sort(key=lambda r:abs(r['spearman']),reverse=True)
 return dict(windows=len(rows),features=len(names),ranking=results)
def main():
 result={}
 for tier in ['screened','strict']:
  rows=json.loads((OUT/(tier+'_windows.json')).read_text());result[tier]=analyze(rows)
  with (OUT/('window_'+tier+'_ranking.csv')).open('w') as f:
   wr=csv.DictWriter(f,fieldnames=list(result[tier]['ranking'][0]));wr.writeheader();wr.writerows(result[tier]['ranking'])
 result['method']={'unit':'one nonoverlapping 3-second window','target':'local camera displacement slope / wheel displacement slope','predictors':'66 IMU/encoder features only','not_predictors':['bag identity','time','run order','camera quality metrics'],'quality':'Existing time alignment and measurement-quality masks retained. Screened is primary; strict is separate sensitivity subset. Never pooled.','nearest_check':'Absolute C difference of nearest-feature windows, excluding self, ties averaged; random-other baseline is all other windows. Descriptive in-sample association, not held-out prediction accuracy.','uncertainty':'Windows may be statistically dependent despite omitting identity. No IID p-values or generalization claim.'}
 (OUT/'window_correlations.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v['ranking'][:10] for k,v in result.items() if k!='method'},indent=2))
if __name__=='__main__':main()
