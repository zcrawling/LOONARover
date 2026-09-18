"""Plot conditional low-frequency consistency results, never corrected odometry."""
import csv,json,argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'data/imu_vibration/odom_v2_analysis');out=p.parse_args().output
 j=json.loads((out/'results.json').read_text());w=list(csv.DictReader((out/'windows.csv').open()));plots=out/'plots';plots.mkdir(exist_ok=True)
 pairs=[r for r in w if r['C_accel'] and r['C_GT'] and r['reference_run']=='False'];fig,ax=plt.subplots(1,2,figsize=(11,4),layout='constrained')
 for a,key,title in [(ax[0],'C_accel','Conditional C_accel vs evaluation C_GT'),(ax[1],'score_mean','Score vs |C_GT - 1|')]:
  x=[float(r[key]) for r in pairs];y=[float(r['C_GT']) if key=='C_accel' else abs(float(r['C_GT'])-1) for r in pairs];a.scatter(x,y);a.set(xlabel=key,ylabel='C_GT' if key=='C_accel' else '|C_GT - 1|',title=title);a.grid(alpha=.2)
 fig.savefig(plots/'gt_comparison.png',dpi=130);plt.close(fig)
 links=[]
 for r in j['runs']:
  rid=r['run_id'];links.append(f'<tr><td><a href="plots/{rid}.png">{rid}</a></td><td>{r["excited_correlation"] if r["excited_correlation"] is not None else "n/a"}</td><td>{r["residual_rms"]:.3f}</td><td>{r["lag_diagnostic"]["lag_s"]*1000:.0f}</td></tr>')
  a=np.genfromtxt(out/'series'/f'{rid}.csv',names=True,delimiter=',',dtype=None,encoding='utf8');t=a['elapsed_s'];good=a['valid']>0;fig,axs=plt.subplots(6,1,figsize=(12,13),sharex=True,layout='constrained')
  for k,cols in enumerate([['vx_encoder','vx_smoothed'],['a_encoder','a_imu_x_fixed_tilt_proxy'],['residual'],['score_long'],['C_accel'],['v1_yaw']]):
   for col in cols:
    yy=np.array([float(x) if str(x) not in ['', 'nan'] else np.nan for x in a[col]]);yy[~good]=np.nan
    if col=='v1_yaw':yy=np.degrees(yy)
    axs[k].plot(t,yy,label=col)
   axs[k].legend(loc='upper right');axs[k].grid(alpha=.2)
  axs[3].axhline(j['config']['score_threshold'],color='red',linestyle='--')
  axs[4].fill_between(t,0,1,where=(a['observability']=='UNOBSERVABLE')&good,transform=axs[4].get_xaxis_transform(),color='gray',alpha=.2,label='UNOBSERVABLE');axs[4].legend(loc='upper right')
  for ax,label in zip(axs,['m/s','m/s²','m/s²','normalized','conditional ratio','degrees']):ax.set_ylabel(label)
  axs[-1].set_xlabel('Elapsed ROS header time (s)');fig.suptitle(rid+'\nFixed-tilt acceleration proxy; gravity not dynamically verified');fig.savefig(plots/f'{rid}.png',dpi=100);plt.close(fig)
 sensitivity=[]
 for f in sorted(out.glob('sensitivity_*/results.json')):
  z=json.loads(f.read_text());sensitivity.append(f'<li>{z["config"]["cutoff"]} Hz: paired n={z["stats"]["n_paired_excited"]}, C rho={z["stats"]["C_spearman"]:.3f}, score rho={z["stats"]["score_mismatch_spearman"]:.3f}</li>')
 examples=[r for r in j['runs'] if r['normal_reference'] or '170809_' in r['run_id']]
 text=f'''<!doctype html><meta charset="utf-8"><title>LIMO V2 offline acceleration consistency</title><style>body{{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;line-height:1.6}}img{{width:100%}}table{{border-collapse:collapse;font-size:13px}}th,td{{padding:7px;border:1px solid #ddd}}</style>
 <h1>LIMO V2: transient longitudinal inconsistency</h1><p><b>가감속 파형의 대응은 확인됐다. 그러나 기존 데이터에서 slip 배율 추정 가능성은 입증되지 않았다.</b> 정지·자세 일정 조건의 임시 가속도 비교이며 완성된 중력 보정 acceleration이 아니다. V1 yaw와 encoder vx는 변경하지 않았다.</p>
 <h2>현재 데이터의 핵심 한계</h2><p>처리한 {len(j['runs'])}개 bag 모두 /imu orientation의 quaternion x/y가 0이다(yaw-only). acceleration norm은 정지에서도 약 10 m/s²로 중력을 포함한다. 작은 orientation covariance는 실제 roll/pitch가 들어 있다는 근거가 아니다. 기록된 topic 목록은 JSON에 포함했다.</p>
 <p>따라서 base_link 회전 변환 후 초기 정지 ax 평균을 뺀 <code>a_imu_x_fixed_tilt_proxy</code>를 사용했다. 이 값은 초기 자세가 유지될 때만 body longitudinal acceleration 근사다. pitch가 1°만 바뀌어도 약 0.17 m/s²의 중력 투영 차이가 생긴다. 동적 pitch를 확인할 수 없어 residual을 slip이라고 단정할 수 없다. gyro tilt 적분을 추가해 보정 완료라고 주장하지 않는다. IMU 장착 위치의 회전 유발 가속도와 미측정 측방속도도 잔차 원인이다.</p>
 <h2>방법과 정합</h2><p>원본 encoder vx → 3차 Butterworth 2 Hz zero-phase LPF → 0.21초 2차 Savitzky–Golay derivative. IMU proxy도 같은 LPF. 공통 100 Hz header 시간축, 누락 구간별 독립 처리, 양 끝 1초 제외. zero-phase/central derivative는 offline 전용이며 미래 샘플을 사용한다. C window는 1초 비중첩이다.</p>
 <p>기존 no_slip=true 메타데이터가 있는 평지 2m 전진·후진 두 기록을 reference로 고정했다. GT나 residual 크기로 정상 구간을 고르지 않았다. 이 라벨은 완전한 무슬립 실측 보증은 아니다. 가감속 cross-correlation에서 각각 −40/−30 ms의 apparent IMU lag가 나와 공통 {j['delay_applied_s']*1000:.0f} ms를 적용했다(음수: IMU가 앞섬). target별 최적 지연으로 잔차를 줄이지 않았다. 이는 wheel/body 동역학과 sensor latency를 분리한 하드웨어 보정값이 아니다.</p>
 <p>정렬 후 reference 가감속 상관은 전진 0.936, 후진 0.999. 높은 상관은 amplitude 일치와 같지 않으며 RMS residual은 각각 0.117, 0.025 m/s². 두 정상 참조의 유효 저주파 residual 표준편차 sigma={j['sigma_normal']:.5f} m/s². score=|residual|/sigma; 3 초과 표시는 통계적으로 교정된 slip 확률이 아니다.</p>
 <h2>관측 가능성과 GT 비교</h2><p>전체 {len(w)}개 window 중 {sum(r['excitation']=='UNOBSERVABLE' for r in w)}개는 encoder acceleration RMS &lt;0.03 m/s²라 UNOBSERVABLE. 해당 C는 빈 값으로 저장했다. 나머지도 GRAVITY_UNVERIFIED이며 C는 조건부 diagnostic이다. C=Σ(ae·ai)/Σ(ae²), vx에 적용하지 않는다.</p>
 <p>평가 가능한 GT + excitation window는 {j['stats']['n_paired_excited']}개, {j['stats']['paired_runs']}개 기록에 걸쳐 있다. C_accel–C_GT Spearman rho={j['stats']['C_spearman']:.3f}; score–|C_GT−1| rho={j['stats']['score_mismatch_spearman']:.3f}. 이 수치로 유효한 C 추정을 주장할 수 없다. window가 bag 전체의 동일 지형을 대표한다는 가정은 없으며, 같은 기록 내 window도 통계적으로 독립이라고 간주하지 않는다.</p>
 <img src="plots/gt_comparison.png"><p>GT는 평가에만 사용. 전후 시계 offset 차이 ≤0.1초, 초기 tag +X 축, 유효 검출·재투영 ≤1.5 px, gap ≤0.25초, encoder 변위 ≥0.02m 조건. C_GT는 진행방향 투영 거리비이며 곡선 경로 길이와 같지 않다. 촬영 exposure 지연과 태그 자세/거리 오차가 남아 있어 실제 slip label은 아니다. 특히 가감속 window의 GT 오차는 C 비교를 흔들 수 있다.</p>
 <h2>필터 민감도</h2><ul>{''.join(sensitivity)}</ul><p>필터 선택으로 가장 좋은 상관만 골라 결론을 내리지 않았다.</p>
 <h2>성공 기준 판정</h2><ol><li>정상 가감속 파형 대응: 조건부 확인. 전진 진폭 잔차는 남음.</li><li>실제 slip에서 score 증가: 미입증. 중력/자세와 독립적인 slip GT가 충분하지 않음.</li><li>C_accel과 C_GT 관계: 현재 비교에서 지지되지 않음.</li><li>등속 common-mode slip: acceleration excitation 부족으로 C를 출력하지 않음. score가 낮아도 무슬립이라는 뜻이 아님.</li></ol>
 <p><b>V2.1 vx correction에 적용할 근거는 아직 없다.</b> 이번 결과는 저주파 불일치 진단의 조건부 출력이다. 새 데이터 수집이나 로버 SW 변경은 하지 않았다.</p>
 <h2>기록별 그래프</h2><table><tr><th>기록</th><th>가속 구간 상관</th><th>Residual RMS</th><th>진단 lag ms (개별 적용 안함)</th></tr>{''.join(links)}</table>
 {''.join(f'<img src="plots/{r["run_id"]}.png">' for r in examples)}<p><a href="windows.csv">Window CSV</a> · <a href="results.json">설정·진단·제외 내역</a></p>'''
 (out/'report.html').write_text(text);print(out/'report.html')
if __name__=='__main__':main()
