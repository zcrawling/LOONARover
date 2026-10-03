"""Compare user's C1/C2 formulas on the same archived acceleration window."""
import csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'data/apriltag_gt/c_vision_비험지_cruise2';out=p/'formula_comparison';out.mkdir(exist_ok=True)
w=next(json.loads(x) for x in (p/'rover/estimate/windows.jsonl').read_text().splitlines() if json.loads(x)['kind']=='acceleration')
r=w['rows'];t=np.array([x['t'] for x in r]);v=np.array([x['vx_encoder'] for x in r]);a=np.array([x['a_corrected'] for x in r]);dt=np.diff(t)
assert np.all(dt>0) and max(dt)<.08
integ=lambda x:np.r_[0,np.cumsum((x[1:]+x[:-1])*.5*dt)]
vi=integ(a);assert np.allclose(vi,[x['v_imu'] for x in r])
se=integ(v);si=integ(vi);den=np.cumsum(v*v)
c1=np.divide(np.cumsum(v*vi),den,out=np.full(len(t),np.nan),where=den>0)
c2=np.divide(si,se,out=np.full(len(t),np.nan),where=abs(se)>0)
# Common display/evaluation support; no individual velocity clipping in either formula.
valid=(den>=.02)&(se>=.01)&(np.arange(len(t))>=14)
g=np.array([[float(x[k]) for k in ['t_ros','gt_x']] for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/localization/dr'])
def interp(q):
 i=np.searchsorted(g[:,0],q)
 if i<1 or i>=len(g) or g[i,0]-g[i-1,0]>.25:return np.nan
 return np.interp(q,g[:,0],g[:,1])
gt=np.array([interp(q) for q in t])-interp(t[0]);cg=np.divide(gt,se,out=np.full(len(t),np.nan),where=se>0)
valid &= np.isfinite(gt)
c1[~valid]=np.nan;c2[~valid]=np.nan;cg[~valid]=np.nan
errors=[(c1-cg),(c2-cg)];derr=[(se-gt)*100,(c1*se-gt)*100,(c2*se-gt)*100]
plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(3,1,figsize=(10,10),sharex=True,layout='constrained');tt=t-t[0]
colors=['#1864ab','#d9480f'];labels=['C1','C2']
for c,color,label in zip([c1,c2],colors,labels):axes[0].plot(tt,c,color=color,label=label,lw=2)
axes[0].plot(tt,cg,color='#343a40',ls='--',label='AprilTag C_GT');axes[0].set_ylabel('C');axes[0].set_title('비험지 · cruise2 | 같은 가속 구간, 같은 IMU 전처리')
for e,color,label in zip(errors,colors,labels):axes[1].plot(tt,e,color=color,label=label,lw=2)
axes[1].axhline(0,color='gray',ls=':');axes[1].set_ylabel('오차')
axes[2].plot(tt,np.where(valid,derr[0],np.nan),color='#868e96',ls='--',label='무보정 encoder')
for e,color,label in zip(derr[1:],colors,labels):axes[2].plot(tt,e,color=color,label=label,lw=2)
axes[2].axhline(0,color='gray',ls=':');axes[2].set(xlabel='가속 시작 후 시간 (s)',ylabel='전진 변위 오차 (cm)')
for ax in axes:ax.grid(alpha=.2);ax.legend(loc='best')
fig.suptitle('누적 구간 [가속 시작, t]의 C 및 전진 변위 오차',fontsize=15)
fig.savefig(out/'errors.png',dpi=160);plt.close(fig)
summary=dict(trial=p.name,scope='acceleration prefix [start,t], not independent holdout or actual corrected odometry',formula_1='sum(v_encoder*v_imu)/sum(v_encoder**2), all samples, no per-sample speed mask',formula_2='trapz(v_imu)/trapz(v_encoder)',preprocessing='archived pre-STOP static forward offset; no new gyro gravity compensation',start_ros=float(t[0]),end_ros=float(t[-1]),display_min_encoder_m=.01,GT_gap_limit_s=.25,C1=float(c1[-1]),C2=float(c2[-1]),C_GT=float(cg[-1]),encoder_m=float(se[-1]),GT_m=float(gt[-1]),C_error_1=float(errors[0][-1]),C_error_2=float(errors[1][-1]),distance_error_cm_encoder=float(derr[0][-1]),distance_error_cm_1=float(derr[1][-1]),distance_error_cm_2=float(derr[2][-1]),note='C*encoder distance is retrospectively rescaled displacement for the same prefix. Not a causal odom trajectory. Full run previously C_unreliable=true; deceleration C=-1.605. Camera receipt/exposure delay uncalibrated. GT used only for evaluation.')
(out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
with (out/'series.csv').open('w') as f:
 writer=csv.writer(f);writer.writerow(['t_ros','elapsed_s','v_encoder','v_imu','s_encoder','s_imu','s_GT','C1','C2','C_GT','C_error_1','C_error_2','distance_error_encoder_cm','distance_error_1_cm','distance_error_2_cm','valid'])
 writer.writerows(zip(t,tt,v,vi,se,si,gt,c1,c2,cg,*errors,*derr,valid))
print(json.dumps(summary,indent=2,ensure_ascii=False))
