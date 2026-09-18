"""Render the saved offline results; no sensor access."""
import csv,json,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'data/imu_vibration/odom_v1_analysis');out=p.parse_args().output
 data=json.loads((out/'results.json').read_text());runs=[r for r in data['runs'] if r['status']=='processed'];plots=out/'plots';plots.mkdir(exist_ok=True)
 rows=[]
 for r in runs:
  rid=r['run_id'];a=np.genfromtxt(out/'series'/f'{rid}.csv',delimiter=',',names=True);t=a['elapsed_s'];fig,ax=plt.subplots(4,1,figsize=(12,11),layout='constrained')
  for seg in np.unique(a['segment']):
   m=a['segment']==seg;tt=t[m]
   ax[0].plot(tt,np.degrees(a['wz_encoder'][m]),color='tab:orange',label='Encoder wz' if seg==0 else None);ax[0].plot(tt,np.degrees(a['wz_imu'][m]),color='tab:blue',label='Bias-corrected gyro wz' if seg==0 else None)
   ax[1].plot(tt,np.degrees(a['yaw_residual'][m]),alpha=.3,color='gray');ax[1].plot(tt,np.degrees(a['residual_mean'][m]),color='black',label='Trailing residual mean' if seg==0 else None)
   ax[2].plot(tt,np.degrees(a['yaw_encoder'][m]),color='tab:orange',label='Encoder integral' if seg==0 else None);ax[2].plot(tt,np.degrees(a['yaw_v1'][m]),color='tab:blue',label='V1 gyro integral' if seg==0 else None);ax[2].plot(tt,np.degrees(a['recorded_yaw'][m]),'--',color='tab:green',label='Recorded wheel pose yaw' if seg==0 else None)
   ax[3].plot(a['x_encoder'][m],a['y_encoder'][m],color='tab:orange',label='Encoder' if seg==0 else None);ax[3].plot(a['x_v1'][m],a['y_v1'][m],color='tab:blue',label='V1' if seg==0 else None);ax[3].plot(a['recorded_x'][m],a['recorded_y'][m],'--',color='tab:green',label='Recorded wheel pose' if seg==0 else None)
  lim=np.degrees(data['config']['residual_threshold'])
  for y in [-lim,lim]:ax[1].axhline(y,color='red',linestyle='--')
  for k in range(3):
   ax[k].fill_between(t,0,1,where=a['suspect']>0,transform=ax[k].get_xaxis_transform(),color='red',alpha=.08);ax[k].set_xlabel('Elapsed ROS header time (s)')
  for k,label in enumerate(['Angular rate (deg/s)','Residual (deg/s)','Accumulated yaw (deg)','Y (m)']):ax[k].set_ylabel(label);ax[k].grid(alpha=.2);ax[k].legend(loc='best')
  ax[3].set_xlabel('X (m)');ax[3].axis('equal');fig.suptitle(rid+'\nIdentical encoder vx; red shading = residual suspect');fig.savefig(plots/f'{rid}.png',dpi=110);plt.close(fig)
  gt=r.get('manual_yaw_gt',{}).get('deg','—');rows.append(f'<tr><td><a href="plots/{rid}.png">{rid}</a></td><td>{r["encoder_yaw_deg"]:.2f}</td><td>{r["v1_yaw_deg"]:.2f}</td><td>{r["yaw_difference_deg"]:.2f}</td><td>{gt}</td><td>{100*r["suspect_fraction"]:.1f}%</td><td>{r["bias_degps"]:.4f}</td></tr>')
 today=[r for r in runs if '20260910' in r['run_id']];d=np.abs([r['yaw_difference_deg'] for r in today]);phase=max(r['header_phase_abs_p95_ms'] for r in runs)
 static=next(r for r in runs if 'stationary_90' in r['run_id'])
 examples=[r for r in runs if '30deg' in r['run_id'] or '160429_' in r['run_id'] or '170809_' in r['run_id']]
 gtrows=[]
 for r in runs:
  g=r['gt']
  if g['status']=='longitudinal_projection_only':gtrows.append(f'<tr><td>{r["run_id"]}</td><td>{g["duration_s"]:.2f}</td><td>{g["GT_delta_m"]:.3f}</td><td>{g["encoder_x_error_m"]*1000:.1f}</td><td>{g["v1_x_error_m"]*1000:.1f}</td></tr>')
 content=f'''<!doctype html><meta charset="utf-8"><title>LIMO offline odometry V1</title><style>body{{font:16px system-ui;max-width:1250px;margin:32px auto;padding:0 20px;line-height:1.6}}table{{border-collapse:collapse;font-size:13px}}td,th{{padding:7px;border:1px solid #ddd}}img{{width:100%}}code{{background:#eee}} </style>
 <h1>LIMO 4WD: encoder + gyro odometry V1</h1><p>기존 bag 44개 중 {len(runs)}개 처리. 센서 누락 1개 및 사용자 지정 uphill 1개 제외. 새 수집·로버 설정 변경 없음.</p>
 <p><b>회전 yaw 개선 가능성이 뚜렷하다.</b> 약 +28° 실측: encoder +69.71° → V1 +26.35°. 약 −28° 실측: encoder −61.13° → V1 −26.72°. 실측 메모가 대략적인 값이므로 1–2° 수준의 정확도를 확정하지 않는다.</p>
 <p>9월 10일 {len(today)}개 기록의 최종 encoder–V1 yaw 차이 절댓값: 중앙값 {np.median(d):.2f}°, 범위 {min(d):.2f}–{max(d):.2f}°. 이것은 두 추정기의 불일치이며 실제 오차 측정이 아니다. bag이 같은 노면이라는 가정은 사용하지 않는다.</p>
 <h2>재처리 및 시간·바이어스</h2><p>vx는 원본 그대로다. baseline은 encoder vx/wz, V1은 같은 vx와 base_link로 변환한 bias 보정 gyro wz를 같은 적분기로 처리했다. 원본 wheel pose도 CSV와 그래프에 별도 보존한다. 센서 header time의 공통 구간을 100 Hz로 보간하며 IMU 40 ms / wheel 80 ms 초과 누락은 연결하지 않는다.</p>
 <p>encoder 각 샘플에 가장 가까운 IMU header의 시차 |P95|는 모든 run에서 {phase:.3f} ms 이하. 기록된 receive−header 및 회전 상호상관 진단은 results.json에 저장했다. <b>샘플 시차는 실제 센서 지연과 다르다.</b> 별도 측정 가능한 고정 지연은 확인되지 않아 임의의 cross-correlation shift를 적용하지 않았다. 알려진 지연만 --gyro-delay로 보정 가능하다. 이 데이터만으로 하드웨어 내부 지연이 0이라고 입증할 수 없다.</p>
 <p>명령 0 + wheel 정지 구간 양 끝 0.2초를 제외하고 gyro 평균을 제거했다. 시작 전 정지를 우선하고, 자체 정지가 없는 초기 4개 기록은 1시간 이내 실제 정지 측정 참조를 사용했다(각 출처 JSON). 90초 정지 기록의 bias는 {static['bias_degps']:.5f}°/s, 정지 표준편차 {static['static_std_degps']:.5f}°/s. 이 정지 기록 자체의 보정 후 0°는 평균 제거 결과이며 독립 검증이 아니다.</p>
 <h2>Suspect 판정</h2><p>residual = encoder wz − 보정 gyro wz. 기본값은 뒤쪽 0.25초 평균의 절댓값 &gt; 0.05 rad/s일 때 이동 중 suspect 표시. normalized score = |평균 residual| / max(정지 residual 표준편차, 0.01 rad/s). 임계값은 변경 가능하며 확정된 slip 판별기가 아니다. wheel separation/scale 오차·양자화·동역학도 residual을 만든다. residual은 V1의 입력을 스위칭하지 않는다.</p>
 <h2>전체 결과</h2><p>yaw 단위 °, bias 단위 °/s. 각 이름을 누르면 시간 그래프와 XY 경로를 볼 수 있다.</p><table><tr><th>기록</th><th>Encoder yaw</th><th>V1 yaw</th><th>차이</th><th>근사 실측</th><th>Suspect 이동 비율</th><th>Bias</th></tr>{''.join(rows)}</table>
 <h2>AprilTag 평가 한계</h2><p>저장된 GT는 초기 태그 축에 대한 이동량과 부호 없는 3D 회전량이다. 따라서 signed planar yaw와 횡방향 오차의 GT로 사용할 수 없다. 아래는 전후 시계 offset이 안정적인 기록에서, 재투영 오차 ≤1.5 px이고 프레임 간격 ≤0.25초인 가장 긴 연속 구간의 <b>진행방향 투영값만 참고 비교</b>한 것이다. 시작 body X와 태그 축 정렬을 가정하며 exposure 지연, GT 자세 품질을 완전히 검증한 정확도 시험은 아니다. 실패 디렉터리 기록도 같은 기준으로 부분 구간을 표시한다. GT는 bias·시간 센서 정합·적분 입력에 사용하지 않았다.</p><table><tr><th>기록</th><th>구간 s</th><th>GT m</th><th>Encoder 투영오차 mm</th><th>V1 투영오차 mm</th></tr>{''.join(gtrows)}</table>
 <p><b>결론:</b> encoder yaw의 큰 누적오차를 gyro yaw로 줄이는 V1은 기존 회전 실측과 부합한다. vx를 바꾸지 않으므로 공통 종방향 slip은 해결하지 않는다. 지금 결과는 differential slip의 원인 식별이나 전체 위치 정확도 개선을 확정하는 결과가 아니다.</p>
 <h2>대표 시간 그래프</h2>{''.join(f'<img src="plots/{r["run_id"]}.png" alt="{r["run_id"]}">' for r in examples)}
 <p><a href="summary.csv">요약 CSV</a> · <a href="results.json">설정·정합·GT·제외 기록 JSON</a></p>'''
 (out/'report.html').write_text(content)
 print('Report:',out/'report.html')
if __name__=='__main__':main()
