"""Audit six existing C/vision trials, without changing estimator outputs."""
import csv,json
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[3];base=root/'data/apriltag_gt';out=base/'c_analysis_20260916';out.mkdir(exist_ok=True)
paths=[base/('c_vision_'+label+'_cruise'+str(n)) for label in ['비험지','험지_돌바닥','험지_돌바닥2'] for n in [1,2]]
labels=['Smooth 1s','Smooth 2s','Stone 1s','Stone 2s','Stone2 1s','Stone2 2s'];summary=[]
fig,axes=plt.subplots(2,3,figsize=(14,8),layout='constrained')
report=['# C 추정 / AprilTag 6회 시험 분석','세 노면에서 cruise 1초·2초 각 1회. 최고 명령속도 0.25 m/s, ramp/decel 각 2.5초. 기존 출력은 변경하지 않고 저장된 window에서 적분·회귀를 독립 재계산했다.','**현재 C 추정은 채택하기 어렵다.** 6회 모두 최종 unreliable. GT를 비교할 수 있는 가속 5회 중 1회만 C 오차 1% 미만이며, 나머지는 7.8–44.1%. 감속은 전반적으로 불일치. 이는 현재 static-bias 기반 실험의 결과이며 IMU를 쓰는 모든 방식이 불가능하다는 결론은 아니다.','|노면 / cruise|C_acc|C_GT(acc)|C_dec|C_GT(dec)|C 적용 샘플|V1 마지막 차이 cm|Test 마지막 차이 cm|','|---|---:|---:|---:|---:|---:|---:|---:|']
for i,(p,label) in enumerate(zip(paths,labels)):
 rows=list(csv.DictReader((p/'rover/estimate/samples.csv').open()));windows=[json.loads(s) for s in (p/'rover/estimate/windows.jsonl').read_text().splitlines()];comparison=json.loads((p/'c_comparison.json').read_text());evaluation=json.loads((p/'evaluation/evaluation.json').read_text());frames=list(csv.DictReader((p/'camera/frames.csv').open()));cfg=json.loads((p/'test.json').read_text())
 acc=[r for r in rows if r['phase']=='ACCEL'];cruise=[r for r in rows if r['phase']=='CRUISE'];moving=[r for r in rows if r['phase']!='STOP'];bad=[r for r in moving if r['acceleration_valid']=='False']
 a,d=comparison['windows'];bias_delta=float(rows[-1]['accel_bias'])-float(acc[0]['accel_bias'])
 rec=dict(trial=p.name,acc=a,dec=d,applied_samples=sum(r['C_valid']=='True' for r in rows),invalid_motion_samples=len(bad),invalid_yaw_over_threshold=sum(abs(float(r['wz']))>.05 for r in bad),stationary_bias_change=bias_delta,cruise_mean_accel=float(np.mean([float(r['a_corrected']) for r in cruise])),cruise_mean_encoder_accel=(float(cruise[-1]['vx_encoder'])-float(cruise[0]['vx_encoder']))/(float(cruise[-1]['t'])-float(cruise[0]['t'])),camera_status=dict(Counter(r['reason'] for r in frames)),clock_offset_change_ms=1000*(cfg['clock_after']['best']['offset_s']-cfg['clock_before']['best']['offset_s']),evaluation=evaluation)
 for window in windows:
  z=window['rows'];t=np.array([r['t'] for r in z]);v=np.array([r['vx_encoder'] for r in z]);ac=np.array([r['a_corrected'] for r in z]);vi=np.r_[0,np.cumsum(np.diff(t)*(ac[1:]+ac[:-1])/2)]
  if window['kind']=='deceleration':vi-=vi[-1]
  m=abs(v)>=.02;raw=float(v[m]@vi[m]/(v[m]@v[m]));assert abs(raw-window['C_raw'])<1e-9
  rec[window['kind']+'_max_dt_s']=float(max(np.diff(t)))
 summary.append(rec)
 def fmt(x):return 'N/A' if x is None else f'{x:.3f}'
 report.append(f"|{p.name.removeprefix('c_vision_')}|{fmt(a['C_estimate'])}|{fmt(a['C_GT'])}|{fmt(d['C_estimate'])}|{fmt(d['C_GT'])}|{rec['applied_samples']}|{evaluation['baselines']['/localization/dr']['last_m']*100:.2f}|{evaluation['odom_c_test']['last_m']*100:.2f}|")
 ax=axes.flat[i];t0=float(acc[0]['t']);tt=np.array([float(r['t'])-t0 for r in rows]);ax.plot(tt,[float(r['vx_encoder']) for r in rows],label='Encoder vx',color='black')
 for w in windows:ax.plot([r['t']-t0 for r in w['rows']],[r['v_imu'] for r in w['rows']],label='IMU '+w['kind'])
 ax.set(title=label,xlabel='Time from ramp start (s)',ylabel='Velocity (m/s)',xlim=(-.5,11),ylim=(-.65,1.15));ax.axhline(0,color='gray',linewidth=.5);ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.savefig(out/'integrated_velocity.png',dpi=130);plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
for ax,key,title in zip(axes,['acc','dec'],['Acceleration coefficient','Deceleration coefficient']):
 x=np.arange(6);ax.bar(x-.18,[r[key]['C_estimate'] for r in summary],.35,label='IMU raw C');ax.bar(x+.18,[r[key]['C_GT'] if r[key]['C_GT'] is not None else np.nan for r in summary],.35,label='Vision C_GT');ax.set_xticks(x,labels,rotation=25);ax.axhline(1,color='gray',linestyle='--');ax.set(title=title,ylabel='C');ax.legend();ax.grid(axis='y',alpha=.2)
fig.savefig(out/'coefficients.png',dpi=130);plt.close(fig)
report+=['','![C 비교](coefficients.png)','![적분 속도](integrated_velocity.png)','## 해석','- 돌바닥 4회는 C가 단 한 샘플에도 적용되지 않았다. 움직이는 동안 유효하지 않은 acceleration 샘플은 모두 |V1 wz| > 0.05 rad/s 조건에 걸렸다. 데이터 수신 실패로 단정하면 안 된다. 이력상 run_bad가 유지돼 이후 encoder fallback한다. 동일한 V1/test 결과는 보정 성공을 의미하지 않는다.','- 매끈한 바닥 cruise1에서는 실제 적용 후 마지막 차이가 2.19→7.52 cm로 악화됐다. cruise2에서는 3.05→2.44 cm로 소폭 개선됐지만 C_dec=-1.605이므로 run 전체 신뢰성 검증은 실패했다.','- 출발·종료 정지 구간 forward acceleration 평균 차이는 -0.187~+0.167 m/s². 의도한 명령 가속도는 0.1 m/s²이다. 따라서 정지에서 한 번 뺀 오프셋이 전체 주행에 유효하다는 가정이 성립하지 않는 정황이 강하다. 이는 전자적 bias 변화만을 뜻하지 않으며 자세/중력 투영, 차체 진동, 좌표변환·측정 오차를 포함할 수 있다.','- 매끈한 바닥에서도 cruise 보정 acceleration 평균이 +0.073/+0.118 m/s²다. 감속 후 정지 확인 대기까지 이 오프셋을 적분하므로 C_dec가 음수가 될 수 있다. 부호 공식 오류 여부는 저장된 acceleration으로 독립 재적분하여 확인했으며 기존 결과와 일치했다. 물리적 원인을 단독으로 확정한 것은 아니다.','- 측정 가능한 C_GT(acc)는 1.011–1.031, C_GT(dec)는 1.031–1.064다. 현재 시험에서는 큰 longitudinal wheel overestimate/slip 라벨 분포가 보이지 않는다. 카메라 scale/투영/타이밍 오차도 포함되므로 이를 모두 encoder 교정 정답으로 확정하면 안 된다.','## 데이터 제한','돌바닥 cruise1은 가속·감속 endpoint GT가 없어 해당 C_GT를 평가할 수 없다. 위치 오차도 관측된 subset 기준이다. 나머지 결과 역시 camera receipt와 노출 시각은 같지 않으며, 평지 cruise1 clock offset 전후 변화가 24.44 ms로 가장 크다. 가속 ramp window의 최대 sample 간격은 모두 약 21 ms로 큰 timestamp gap은 관측되지 않았다.','각 노면/프로파일당 한 번이므로 노면별 일반화를 주장할 수 없다. C_acc와 C_GT 비교는 평균 displacement ratio와 velocity-regression coefficient의 비교이며 C가 시간에 따라 변하면 두 정의가 달라질 수 있다.','## 다음 판단','현재 C를 baseline에 반영하지 않는다. 먼저 실제 full attitude 기반 gravity compensation 또는 고정 자세가 검증된 입력에서 accel consistency를 확인해야 한다. yaw gate를 완화하는 것만으로 raw C 불일치는 해결되지 않는다. 기존 데이터로 원인 분석은 가능하지만, 현재 결과만으로 IMU C가 slip을 추정했다고 주장할 수 없다.','## 원본']
for p in paths:report.append(f'- [{p.name}](../{p.name}/report.html) · [window 원본](../{p.name}/rover/estimate/windows.jsonl)')
(out/'report.md').write_text('\n\n'.join(report));(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(out/'report.md')
