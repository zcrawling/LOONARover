"""C1/C2 prefix estimates on two stone acceleration windows, no GT fitting."""
import csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'data/apriltag_gt/stone_c_time';out.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(2,1,figsize=(10,8),sharex=True,sharey=True,layout='constrained');results=[]
for ax,suffix in zip(axes,['cruise1','cruise2']):
 p=ROOT/'data/apriltag_gt'/('c_vision_험지_돌바닥_'+suffix)
 w=next(json.loads(x) for x in (p/'rover/estimate/windows.jsonl').read_text().splitlines() if json.loads(x)['kind']=='acceleration')
 r=w['rows'];t=np.array([x['t'] for x in r]);v=np.array([x['vx_encoder'] for x in r]);a=np.array([x['a_corrected'] for x in r]);dt=np.diff(t)
 assert (dt>0).all() and max(dt)<.08
 integrate=lambda x:np.r_[0,np.cumsum((x[1:]+x[:-1])*.5*dt)]
 vi=integrate(a);assert np.allclose(vi,[x['v_imu'] for x in r])
 se=integrate(v);si=integrate(vi);den=np.cumsum(v*v)
 c1=np.divide(np.cumsum(v*vi),den,out=np.full(len(t),np.nan),where=den>0)
 c2=np.divide(si,se,out=np.full(len(t),np.nan),where=se>0)
 valid=(den>=.02)&(se>=.01)&(np.arange(len(t))>=14)
 g=np.array([[float(x[k]) for k in ['t_ros','gt_x']] for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/localization/dr'])
 def interp(q):
  i=np.searchsorted(g[:,0],q)
  if i<1 or i>=len(g) or g[i,0]-g[i-1,0]>.25:return np.nan
  return np.interp(q,g[:,0],g[:,1])
 gt=np.array([interp(q) for q in t])-interp(t[0]);cg=np.divide(gt,se,out=np.full(len(t),np.nan),where=se>0)
 c1[~valid]=np.nan;c2[~valid]=np.nan;cg[~valid]=np.nan
 ax.axhline(0,color='gray',lw=.8);ax.axhline(1,color='gray',ls=':',lw=1,label='C=1 기준')
 ax.plot(t-t[0],c1,color='#1864ab',lw=2,label='① 속도 회귀 C1')
 ax.plot(t-t[0],c2,color='#d9480f',lw=2,label='② 거리 비율 C2')
 if np.isfinite(cg).any():ax.plot(t-t[0],cg,color='#343a40',ls='--',label='AprilTag C_GT')
 else:ax.text(.03,.94,'시작 GT 누락: C_GT 비교 불가',transform=ax.transAxes,va='top',fontsize=10)
 ax.set(title='돌바닥 · '+suffix,ylabel='C (무차원)',xlim=(0,2.65));ax.grid(alpha=.2);ax.legend(loc='lower left',fontsize=9)
 ax.annotate(f'C1={c1[-1]:.3f}\nC2={c2[-1]:.3f}',xy=(t[-1]-t[0],c2[-1]),xytext=(-105,22),textcoords='offset points',bbox=dict(facecolor='white',alpha=.85,edgecolor='#ddd'),arrowprops=dict(arrowstyle='-',color='gray'))
 results.append(dict(trial=p.name,C1=float(c1[-1]),C2=float(c2[-1]),C_GT=float(cg[-1]) if np.isfinite(cg[-1]) else None,first_valid_elapsed_s=float(t[valid][0]-t[0]),duration_s=float(t[-1]-t[0])))
 with (out/(suffix+'.csv')).open('w') as f:
  cw=csv.writer(f);cw.writerow(['t_ros','elapsed_s','v_encoder','v_imu','C1','C2','C_GT','estimator_plot_valid']);cw.writerows(zip(t,t-t[0],v,vi,c1,c2,cg,valid))
axes[-1].set_xlabel('가속 시작 후 시간 (s)')
fig.suptitle('가속 시작부터 t까지 누적 계산한 C 추정값',fontsize=16)
fig.supxlabel('동일한 기존 정지 offset 보정 사용 · 새 gyro 중력 보상 없음 · 작은 분모 구간은 표시 제외',fontsize=10)
fig.savefig(out/'c_time.png',dpi=160);plt.close(fig)
(out/'summary.json').write_text(json.dumps(dict(results=results,method='Archived static offset acceleration integrated from v0=0. C1 uses all prefix samples; C2 trapezoidal integral ratio. Plot requires >=15 samples, sum(v²)>=0.02 and encoder distance>=0.01m. GT not used to filter estimator curves. No clipping, no new gravity compensation.'),indent=2,ensure_ascii=False))
print(json.dumps(results,ensure_ascii=False,indent=2))
