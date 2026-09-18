"""Descriptive two-window comparison, not a correlation ranking."""
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parents[3]
out=root/'data/apriltag_gt/analysis_20260909/quality_correlations/screened'
with (out/'samples.csv').open() as f:rows=list(csv.DictReader(f))
assert len(rows)==2
a,b=({k:float(v) for k,v in r.items() if k!='run_id'} for r in rows)
plt.rcParams.update({'font.family':'NanumGothic','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(2,2,figsize=(13,10),gridspec_kw={'width_ratios':[1,1.2]})
fig.suptitle('좋은 구간 2개의 C와 센서 특징 비교',fontsize=18,y=.985)
fig.text(.5,.94,'A: 17:36:36 시험의 3초 구간   →   B: 17:39:50 시험의 3초 구간\n표본 n=2: 특징의 증감 비교이며, 상관의 강도·유의성 순위가 아닙니다.',ha='center',va='top',fontsize=11)
ax=axes[0,0];ax.bar(['A','B'],[a['C'],b['C']],color=['#667788','#2476ad'],width=.5)
for i,v in enumerate([a['C'],b['C']]):ax.text(i,v+.025,f'{v:.4f}',ha='center',fontsize=13)
ax.axhline(1,color='#555555',linestyle='--',lw=1);ax.set_ylim(0,1.25);ax.set_ylabel('C = 카메라 / encoder 이동 배율');ax.set_title('C: +5.80% 변화')
ax=axes[0,1];keys=[f'{axis}_std' for axis in ['ax','ay','az','gx','gy','gz']];rat=[b[k]/a[k] for k in keys]
ax.barh(range(6),rat,color='#2476ad');ax.set_yticks(range(6),['가속도 X','가속도 Y','가속도 Z','각속도 X','각속도 Y','각속도 Z']);ax.invert_yaxis();ax.axvline(1,color='#555555',linestyle='--');ax.set_xlim(0,5.5)
for i,v in enumerate(rat):ax.text(v+.07,i,f'{v:.2f}배',va='center')
ax.set_title('축별 표준편차: B / A');ax.set_xlabel('1배 = 변화 없음 (가속도·각속도 단위는 별개)')
ax=axes[1,0];bands=['2_10','10_25','25_45'];values=np.array([[b[f'{axis}_power_{band}']/a[f'{axis}_power_{band}'] for band in bands] for axis in ['ax','ay','az','gx','gy','gz']])
im=ax.imshow(np.log2(values),cmap='PuOr_r',vmin=-3,vmax=3,aspect='auto')
for i in range(6):
    for j in range(3):ax.text(j,i,f'{values[i,j]:.2f}배',ha='center',va='center',color='white' if abs(np.log2(values[i,j]))>1.9 else '#222222')
ax.set_xticks(range(3),['2–10 Hz','10–25 Hz','25–45 Hz']);ax.set_yticks(range(6),['ax','ay','az','gx','gy','gz']);ax.set_title('주파수 대역 에너지: B / A')
ax.text(.5,-.12,'숫자는 배율 · 색은 log₂ 배율 (1배 중심)',transform=ax.transAxes,ha='center')
ax=axes[1,1];keys=[f'{axis}_{stat}' for axis in ['vx','wz'] for stat in ['mean','std','ptp','diff_rms']];rat=[b[k]/a[k] for k in keys];labels=['vx 평균','vx 표준편차','vx 진폭','vx 차분 RMS','wz 평균','wz 표준편차','wz 진폭','wz 차분 RMS']
ax.barh(range(8),rat,color='#2476ad');ax.set_yticks(range(8),labels);ax.invert_yaxis();ax.axvline(1,color='#555555',linestyle='--');ax.set_xlim(0,1.35)
for i,v in enumerate(rat):ax.text(v+.02,i,f'{v:.3f}배',va='center')
ax.set_title('wheel odom 특징: B / A');ax.set_xlabel('vx: 선속도 · wz: wheel 기반 각속도')
for ax in axes.flat:
    ax.spines[['top','right']].set_visible(False)
fig.text(.03,.025,'주의: 각속도 X·Z 진동과 일부 대역 에너지는 커졌지만, 이것이 C를 예측한다는 증거는 아닙니다.\n축 이름은 기록된 IMU frame 기준입니다. C 증가를 slip 증가로 직접 해석하지 않습니다.',fontsize=11)
fig.tight_layout(rect=[0,.075,1,.91]);fig.savefig(out/'two_window_comparison.png',dpi=150);fig.savefig(out/'two_window_comparison.svg')
with (out/'two_window_feature_values.csv').open('w') as f:
    writer=csv.writer(f);writer.writerow(['feature','A','B','B_over_A','two_point_r_descriptive_only'])
    for key in list(rows[0])[8:]:writer.writerow([key,a[key],b[key],b[key]/a[key] if a[key] else '',np.sign(b[key]-a[key]) if b[key]!=a[key] else 'undefined'])
