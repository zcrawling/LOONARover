"""Distance-ratio C from archived corrected acceleration; GT evaluation only."""
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'data/apriltag_gt/distance_c_reanalysis';out.mkdir(exist_ok=True)
results=[]
for p in sorted((ROOT/'data/apriltag_gt').glob('c_vision_*')):
 f=p/'rover/estimate/windows.jsonl';metric=p/'c_comparison.json'
 if not f.exists() or not metric.exists():continue
 gt=json.loads(metric.read_text())
 for w in map(json.loads,f.read_text().splitlines()):
  if w['kind']!='acceleration' or len(w['rows'])<3:continue
  r=w['rows'];t=np.array([x['t'] for x in r]);dt=np.diff(t);a=np.array([x['a_corrected'] for x in r]);v=np.array([x['vx_encoder'] for x in r])
  if np.any(dt<=0) or max(dt)>.08:continue
  vi=np.r_[0,np.cumsum((a[1:]+a[:-1])*.5*dt)]
  si=float(np.sum((vi[1:]+vi[:-1])*.5*dt));se=float(np.sum((v[1:]+v[:-1])*.5*dt))
  if abs(se)<.01:continue
  m=next((x for x in gt['windows'] if x['window']=='acceleration'),{})
  row=dict(trial=p.name,C_velocity_LS=w.get('C_raw'),C_distance=si/se,C_GT=m.get('C_GT'),imu_distance_m=si,encoder_distance_m=se,assumption='archived static-bias correction; constant attitude; no independent gravity/bias separation')
  results.append(row);print(p.name, 'LS',round(row['C_velocity_LS'],3) if row['C_velocity_LS'] is not None else None,'distance',round(si/se,3),'GT',m.get('C_GT'))
(out/'results.json').write_text(json.dumps(results,indent=2))
