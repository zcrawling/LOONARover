"""Exclude first 0.5 s from C fitting, retain physical nonzero initial velocity."""
import argparse,csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--trial',default='c_vision_비험지_cruise2')
args=parser.parse_args()
p=ROOT/'data/apriltag_gt'/args.trial;out=p/'formula_comparison_skip_0p5';out.mkdir(exist_ok=True)
w=next(json.loads(x) for x in (p/'rover/estimate/windows.jsonl').read_text().splitlines() if json.loads(x)['kind']=='acceleration')
r=w['rows'];t0=np.array([x['t'] for x in r]);v0=np.array([x['vx_encoder'] for x in r]);a=np.array([x['a_corrected'] for x in r]);dt=np.diff(t0)
assert (dt>0).all() and max(dt)<.08
vi0=np.r_[0,np.cumsum((a[1:]+a[:-1])*.5*dt)]
assert np.allclose(vi0,[x['v_imu'] for x in r])
start=t0[0]+.5;t=np.r_[start,t0[t0>start]]
v=np.interp(t,t0,v0);vi=np.interp(t,t0,vi0)
integ=lambda x:np.r_[0,np.cumsum(np.diff(t)*(x[1:]+x[:-1])*.5)]
se=integ(v);si=integ(vi);den=np.cumsum(v*v)
c1=np.divide(np.cumsum(v*vi),den,out=np.full(len(t),np.nan),where=den>0)
c2=np.divide(si,se,out=np.full(len(t),np.nan),where=se>0)
# Same support policy as previous figure; no early invalid denominators plotted.
valid=(den>=.02)&(se>=.01)&(np.arange(len(t))>=14)
g=np.array([[float(x[k]) for k in ['t_ros','gt_x']] for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/localization/dr'])
def interp_gt(q):
 i=np.searchsorted(g[:,0],q)
 if i<1 or i>=len(g) or g[i,0]-g[i-1,0]>.25:return np.nan
 return np.interp(q,g[:,0],g[:,1])
gt=np.array([interp_gt(q) for q in t])-interp_gt(start)
cg=np.divide(gt,se,out=np.full(len(t),np.nan),where=se>0)
c1[~valid]=np.nan;c2[~valid]=np.nan;cg[~valid]=np.nan
assert np.isfinite([c1[-1],c2[-1]]).all()
tt=t-t0[0];plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False,'font.size':12})
fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained')
for c,color,label in [(c1,'#1864ab','C1'),(c2,'#d9480f','C2')]:
 axes[0].plot(tt,c,color=color,lw=2,label=label)
 axes[1].plot(tt,c-cg,color=color,lw=2,label=label)
if np.isfinite(cg).any():axes[0].plot(tt,cg,color='#343a40',ls='--',label='AprilTag C_GT')
else:axes[1].text(.5,.5,'AprilTag 기준값 누락: 오차 계산 불가',transform=axes[1].transAxes,ha='center')
axes[0].set(ylabel='C',title=p.name.removeprefix('c_vision_').replace('_',' · ')+' | 초기 0.5초 제외')
axes[1].axhline(0,color='gray',ls=':');axes[1].set(ylabel='오차',xlabel='가속 시작 후 시간 (s)')
for ax in axes:ax.grid(alpha=.2);ax.legend();ax.set_xlim(.5,2.55)
fig.suptitle('누적 계산 구간 [0.5초, t]',fontsize=15)
fig.savefig(out/'errors.png',dpi=160);fig.savefig(out/'errors.svg');plt.close(fig)
summary=dict(trial=p.name,skip_s=.5,C1=float(c1[-1]),C2=float(c2[-1]),C_GT=float(cg[-1]),error_C1=float(c1[-1]-cg[-1]),error_C2=float(c2[-1]-cg[-1]),encoder_distance_m=float(se[-1]),GT_distance_m=float(gt[-1]),v_imu_at_cut=float(vi[0]),v_encoder_at_cut=float(v[0]),first_display_s=float(tt[valid][0]),method='C1/C2 sums/integrals start at 0.5s, boundary linearly interpolated. IMU velocity retains integration from departure: initial transient contribution NOT removed from initial velocity. No reset to zero, no encoder/GT velocity substitution. Same static-offset preprocessing, no new gravity correction. 0.5s cutoff supplied by user, not independently identified friction transition.')
summary={k:(None if isinstance(v,float) and not np.isfinite(v) else v) for k,v in summary.items()}
(out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False))
with (out/'series.csv').open('w') as f:
 wr=csv.writer(f);wr.writerow(['elapsed_s','v_encoder','v_imu','C1','C2','C_GT','error_C1','error_C2']);wr.writerows(zip(tt,v,vi,c1,c2,cg,c1-cg,c2-cg))
print(json.dumps(summary,indent=2,ensure_ascii=False))
