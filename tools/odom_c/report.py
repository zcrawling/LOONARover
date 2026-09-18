import argparse,json,csv,base64,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from analyze import read,number
from pipeline import CORE

def main():
 p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);a=p.parse_args();out=a.dataset
 rows=read(out/'windows.csv');summary=json.loads((out/'analysis.json').read_text());audit=json.loads((out/'audit.json').read_text());cor=read(out/'feature_correlations.csv');train=read(out/'training_feature_correlations.csv')
 y=np.array([number(r,'C_GT') for r in rows]);speed=np.array([number(r,'vx_mean') for r in rows])
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
 known=sorted({r['terrain_id'] for r in rows}-{'unknown','mixed'})
 terrain_section='<p><b>Terrain-controlled plots: 미산출.</b> 노면별 구간 라벨이 제공되지 않았다. unknown을 하나의 노면으로 취급하거나 bag 전체에 같은 노면을 추측해 넣지 않았다. terrain_template.json에 명시적 구간 라벨을 입력하면 계산된다.</p>'
 if known:
  fig,axs=plt.subplots(1,len(known),figsize=(4*len(known),3.5),squeeze=False,layout='constrained')
  for ax,terrain in zip(axs[0],known):
   rr=[r for r in rows if r['terrain_id']==terrain];ax.scatter([number(r,'raw_az_std') for r in rr],[number(r,'C_GT') for r in rr],c=[number(r,'vx_mean') for r in rr],cmap='viridis');ax.set_title(terrain);ax.set_xlabel('raw_az_std');ax.set_ylabel('C_GT')
  fig.savefig(out/'terrain_controlled.png',dpi=140);plt.close(fig)
  terrain_section='<p>명시적으로 제공된 terrain metadata 내부의 비교다. unknown/mixed는 이 그림에서 제외했다.</p><img src="data:image/png;base64,'+base64.b64encode((out/'terrain_controlled.png').read_bytes()).decode()+'" alt="Terrain controlled scatter">'
 bins=sorted({r['speed_bin'] for r in rows});fig,axs=plt.subplots(1,len(bins),figsize=(4*len(bins),3.5),squeeze=False,layout='constrained')
 for ax,bin_id in zip(axs[0],bins):
  rr=[r for r in rows if r['speed_bin']==bin_id];ax.scatter([number(r,'raw_az_std') for r in rr],[number(r,'C_GT') for r in rr],s=20);ax.set_title('Speed bin '+bin_id+' | n='+str(len(rr)));ax.set_xlabel('raw_az_std');ax.set_ylabel('C_GT');ax.grid(alpha=.15)
 fig.savefig(out/'speed_bins.png',dpi=140);plt.close(fig)
 names=['raw_az_std','raw_ax_rms','raw_az_kurtosis','vx_mean'];fig,axs=plt.subplots(2,4,figsize=(14,7),layout='constrained')
 for i,mode in enumerate(['raw','detrended']):
  for j,n in enumerate(names):
   f=n.replace('raw_',mode+'_');x=np.array([number(r,f) for r in rows]);ax=axs[i,j];sc=ax.scatter(x,y,c=speed,cmap='viridis',s=18);ax.set_xlabel(f);ax.set_ylabel('C_GT');ax.set_title('Local window pairing');ax.xaxis.set_major_locator(MaxNLocator(4));ax.grid(alpha=.15)
 fig.colorbar(sc,ax=axs,shrink=.7,label='Encoder vx mean (m/s)');fig.suptitle('1 s windows, 0.2 s step: 93 correlated windows (not 93 independent trials)');fig.savefig(out/'feature_scatter.png',dpi=140);plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(12,3.6),layout='constrained');B=np.column_stack([np.ones(len(rows)),speed])
 for ax,n in zip(axs,names[:3]):
  x=np.array([number(r,n) for r in rows]);rx=x-B@np.linalg.lstsq(B,x,rcond=None)[0];ry=y-B@np.linalg.lstsq(B,y,rcond=None)[0]
  ax.scatter(rx,ry,s=20,color='#286b8c');ax.set_xlabel(n+' residual');ax.set_ylabel('C_GT residual');ax.grid(alpha=.2)
 fig.suptitle('Within the only populated speed bin [0.075, 0.15): linear vx adjustment');fig.savefig(out/'speed_controlled.png',dpi=140);plt.close(fig)
 psd=read(out/'psd.csv');fig,axs=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
 for ax,n in zip(axs,['ax','az']):
  for mode in ['raw','detrended']:
   grid=np.arange(1,45.01,.25);stack=[]
   for key in sorted({(r['run_id'],r['segment']) for r in psd}):
    rr=[r for r in psd if (r['run_id'],r['segment'])==key and r['mode']==mode]
    if rr:stack.append(np.interp(grid,[number(r,'frequency_hz') for r in rr],[number(r,n) for r in rr]))
   if stack:ax.semilogy(grid,np.maximum(np.median(stack,axis=0),1e-15),label=mode)
  ax.set_title(n+' median segment PSD');ax.set_xlabel('Hz');ax.set_ylabel('(m/s²)²/Hz');ax.legend();ax.grid(alpha=.2)
 fig.suptitle('Contiguous motion segments, not duplicated sliding windows. No cutoff selected.');fig.savefig(out/'psd.png',dpi=140);plt.close(fig)
 def image(name):return '<img src="data:image/png;base64,'+base64.b64encode((out/name).read_bytes()).decode()+'" alt="'+name+'">'
 def table(rr):return '<table>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rr)+'</table>'
 rr=[['특징','전체 Spearman','전체 속도 통제 순위상관','학습 run 속도 통제 순위상관']]
 for n in list(dict.fromkeys(CORE['raw']+CORE['detrended'])):
  c=next(r for r in cor if r['group']=='all' and r['feature']==n);t=next(r for r in train if r['group']=='all' and r['feature']==n)
  fmt=lambda v:f'{float(v):+.3f}' if v else '해당 없음'
  rr.append([n,fmt(c['spearman']),fmt(c['speed_partial_rank']),fmt(t['speed_partial_rank'])])
 counts=[['Run','사용 창','시계 변화 s','겉보기 지연 s','상태']]
 for r in audit['runs']:
  counts.append([r['run_id'],r.get('accepted',0),round(r.get('clock_change_s',0),3),round(r.get('apparent_lag',{}).get('candidate_camera_lag_s',0),3) if 'apparent_lag' in r else '—',r['status']])
 models=summary['regression_status'];split=json.loads((out/'split.json').read_text())
 if models=='withheld_no_training_relationship':
  result='<p><b>Ridge 학습 보류.</b> 학습용 run에서 사전에 정한 핵심 IMU 후보들의 속도 통제 순위상관 절댓값은 0.21 미만이다. 탐색용 시작 기준 |ρ|≥0.3도 통과하지 못해 사용자 조건인 “관계 확인 후 회귀”에 따라 학습하지 않았다. 이 기준은 통계적 유의성 기준이나 하드웨어 한계가 아니다.</p>'
  m=summary['encoder_only_test_audit'][0]
  result+=f"<p>분리해 둔 test run의 평가 가능한 비중첩 구간 {m['covered_seconds']:.1f}초에서 GT 누적 {m['GT_distance_m']:.4f} m, 엔코더 누적 {m['encoder_distance_m']:.4f} m, 오차 {m['encoder_final_error_m']*1000:.1f} mm ({m['encoder_relative_error']*100:.2f}%). 학습한 C_pred가 없으므로 보정 결과·개선율은 미산출이다. 이는 선별 구간의 합이며 run 전체 최종 오차가 아니다.</p>"
 else:result='<p>Ridge 진단 결과는 analysis.json / test_odometry.csv / leave_one_run_out.csv에 기록했다. 최종 채택은 미확정이다.</p>'
 document=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>IMU + Encoder → C_GT 파이프라인</title><style>body{{max-width:1200px;margin:40px auto;padding:0 22px;font:17px/1.7 sans-serif;color:#21333e}}h1,h2{{line-height:1.3}}h2{{margin-top:38px}}img{{width:100%}}table{{width:100%;border-collapse:collapse;font-size:13px}}td{{padding:8px;border-bottom:1px solid #d1dbe0}}tr:first-child{{background:#edf3f6;font-weight:bold}}.lead{{padding:22px;background:#edf5f8;border-left:5px solid #2b718e}}code{{overflow-wrap:anywhere}}</style>
<h1>동기화된 구간의 IMU·엔코더로 C_GT를 설명할 수 있는가</h1>
<div class="lead">기본 1초 창 / 0.2초 간격으로 93개 학습 후보를 생성했다. 유효 run은 5개이며 모두 약 0.1 m/s, terrain은 미확인이다. raw 통계와 선형 추세 제거 특징을 비교했으나 학습 run에서 핵심 IMU 특징과 C의 속도 통제 관계가 약했다. 이번 자료로 회귀 채택을 정당화하지 않는다. A/B/C/D 중 하나를 억지로 확정하지 않는다.</div>
<h2>동기화와 GT 정의</h2>
<p>IMU와 encoder는 ROS header measurement timestamp를 우선 사용한다. 카메라는 실제 exposure timestamp가 없어 host receipt timestamp를 사용하며 이를 정밀 촬영 시각이라고 부르지 않는다. 전후 SSH 시계 offset을 보간했고 변화가 0.1초를 넘은 run은 제외했다. 카메라와 wheel 속도 비교의 겉보기 지연 후보는 유효 run에서 0~50ms였다. 촬영 지연·차체 응답·슬립이 혼합된 값이므로 자동으로 맞추지 않았다. --camera-delay는 별도로 측정된 값을 전달할 때만 사용한다.</p>
<p>C_GT = Delta_s_GT / Delta_s_encoder. encoder 거리는 longitudinal vx의 사다리꼴 적분이다. GT는 initial tag +X 방향 progress를 각 창 안에서 Huber 선형 적합한 후 같은 t0/t1에서 차이를 계산한다. 3D Euclidean 거리를 쓰지 않는다. 별도 이동평균이나 시간 이동 필터를 적용하지 않았다. 이는 직진·고정 tag mount에서 body displacement를 근사하며 tag/base lever-arm 보정은 아직 검증되지 않았다.</p>
<p>epsilon=0.02 m 이하 encoder 이동은 제외한다. C≈0인 wheel-spin/body-stationary 구간 자체는 제외하지 않도록 구현하고 합성 데이터로 검증했다. C 유효 범위 −0.2~2.0, GT RMS 3 mm, 재투영 1.5 px, 각도 변화 범위 3° 등은 CLI로 변경 가능하며 물리적 slip 한계값이 아니다. 범위 밖 값은 outlier 후보로 보존된다.</p>
<h2>구간별 특징과 C</h2>
<p>각 모델 입력은 IMU 4개 + encoder 6개, 총 10개다. raw/detrended 각각 az 표준편차, ax RMS, az 첨도, gz RMS와 vx 평균/표준편차, 좌우 평균속도, wz 평균, wheel acceleration RMS를 사용한다. 추가 raw/window 통계도 데이터셋에 보존하되 처음부터 모든 특징을 회귀에 넣지 않는다.</p>
{image('feature_scatter.png')}{table(rr)}
<h2>PSD 확인 후에도 임의의 cutoff를 선택하지 않았다</h2>
{image('psd.png')}
<p>PSD는 GT 채택 여부와 별개로 IMU가 연속적인 주행 구간에서 계산했다. X축에는 수 Hz대, Z축에는 약 10여 Hz대의 에너지 봉우리가 보이지만 이를 지형 진동이라고 단정하지 않는다. body motion과 terrain vibration의 인과적 경계는 PSD만으로 확정할 수 없다. 따라서 raw와 선형 detrended residual을 비교한다. detrending은 고주파만 남기는 완전한 필터나 중력·자세 보정과 동일하지 않다. IMU를 속도·위치로 적분하지 않았다.</p>
<h2>속도 통제와 terrain 통제의 범위</h2>
{image('speed_controlled.png')}
<p>채택 창은 모두 speed bin [0.075, 0.15) m/s다. 같은 bin 내부에서 실제 평균 vx에 대한 선형 및 rank 잔차 상관을 계산했다. 이것이 모든 비선형 속도 교란을 제거했다는 뜻은 아니다. 다른 속도 기록은 안정화·GT 품질 조건을 통과한 1초 창이 없어 속도 간 일반화를 평가하지 못했다.</p>
{image('speed_bins.png')}{terrain_section}
<h2>학습·검증·시험은 run 단위로 분리</h2>
{table([['Split','Run IDs']]+[[k,', '.join(v)] for k,v in split.items()])}
<p>정렬된 run 목록의 마지막 1개를 test, 앞의 1개를 validation, 나머지 3개를 train으로 고정했다. 시간이나 bag ID는 predictor가 아니다. 겹치는 창을 random split하지 않는다. 향후 학습 시 scaling은 train에서만, Ridge alpha와 raw/residual 선택은 validation에서만 수행한다. 동일 노면 준비 상태나 날짜까지 독립적인지는 현재 metadata로 확인할 수 없다.</p>
{result}
<p>Ridge fitting/prediction, encoder-only ablation, C=1 및 train-constant baseline, nested leave-one-run-out, C RMSE와 거리 누적 비교 코드는 구현했다. 현재 gate가 통과하지 않아 모델 결과를 꾸며내지 않았다. 거리를 합칠 때는 비중첩 평가 구간만 사용해 0.2초 sliding 창을 중복 적분하지 않는다. 전체 run GT가 검증되지 않으면 전체 최종 오차를 대신 채우지 않는다.</p>
<h2>현재 데이터로 내릴 수 있는 결론</h2>
<p>A(반복 가능한 slip feature)는 아직 지지하지 못한다. B(terrain-adaptive)는 terrain 라벨 부재로 판단할 수 없다. C(속도만 설명)는 속도 범위가 좁아 판단할 수 없다. D(unseen-run 과적합)는 회귀를 학습하지 않아 판정하지 않는다. 지금 결론은 <b>이 데이터와 사전 핵심 특징으로 1초 C 회귀를 진행할 근거가 부족하다</b>이며, 센서 조합 자체의 불가능성을 입증한 것이 아니다.</p>
<p>C&lt;0.95를 임시 slip 조건으로 두면 93개 중 1개 창뿐이고 그마저 검증된 slip 사건이 아니다. |C−1|≤0.03인 39개 창도 GT 기반 임시 분류이며 실측 no-slip 확정값은 아니다. 큰 slip에서 개선되는지 확인하기에는 정답 분포가 부족하다. 카메라 초점/배율 오차도 C에 반영될 수 있다.</p>
<h2>파일과 감사 기록</h2>
{table(counts)}
<p>synchronized/*.csv에는 공통 100Hz 시간축, 원본 전후 measurement timestamp, 신호별 valid mask, 6축 IMU, 좌우 wheel velocity, vx/wz, tag progress, cmd_vel을 기록했다. 큰 누락은 NaN으로 유지한다. motor current는 기록에 없어 생성하지 않았다. windows.csv / rejected_windows.csv / audit.json / feature_correlations.csv / ridge_status.json / runwise_holdout_status.csv / encoder_only_test.csv를 함께 제공한다.</p>
<p>실행: tools/odom_c/pipeline.py → analyze.py → report.py. 원본 bag·카메라 기록과 로버 실행 코드는 변경하지 않았다.</p></html>'''
 (out/'report.html').write_text(document);print('Saved',out/'report.html')
if __name__=='__main__':main()
