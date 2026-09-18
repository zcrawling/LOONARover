"""Compare existing primitive trials; no estimator or robot modifications."""
import csv,json
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[3];base=root/'data/apriltag_gt';out=base/'terrain_comparison_20260914';out.mkdir(exist_ok=True)
trials=[('153137','평지','Flat'),('155603','거친 험지','Rough'),('155940','준험지','Moderate')]
fig,axes=plt.subplots(3,3,figsize=(14,11),layout='constrained');report=['# 평지·험지 primitive 시험 비교','시작 pose만 정렬하며 거리 scale fitting은 하지 않았다. AprilTag는 평가에만 사용한다. 각 환경 1회 시험이므로 일반적인 성능 개선이나 원인을 확정하지 않는다.','|환경|추정기|위치 RMSE(cm)|마지막 위치 차이(cm)|누적 yaw 차이(°)|','|---|---|---:|---:|---:|'];details=[];all_data=[]
for row,(suffix,label,en) in enumerate(trials):
 p=base/('primitive_20260914_'+suffix);a=json.loads((p/'primitive_audit.json').read_text());metrics=json.loads((p/'comparison.json').read_text());rows=list(csv.DictReader((p/'comparison.csv').open()));states=[json.loads(x) for x in (p/'rover/states.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (p/'rover/events.jsonl').read_text().splitlines()];frames=list(csv.DictReader((p/'camera/frames.csv').open()));test=json.loads((p/'test.json').read_text());moves=[x for x in events if x['kind']=='transition' and x['intent']['reason']=='running']
 for m in metrics:report.append(f"|{label}|{m['topic']}|{m['position_rmse_m']*100:.2f}|{m['last_observed_position_error_m']*100:.2f}|{m['last_observed_yaw_error_deg']:.2f}|")
 arrays={topic:np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y','odom_x','odom_y','gt_yaw','odom_yaw']] for r in rows if r['topic']==topic]) for topic in ['/localization/dr','/odometry/filtered']};d=arrays['/localization/dr'];t0=d[0,0]
 axes[row,0].plot(d[:,1],d[:,2],'.',ms=2,label='AprilTag');axes[row,0].set_aspect('equal',adjustable='datalim')
 for topic,x in arrays.items():
  err=np.linalg.norm(x[:,3:5]-x[:,1:3],axis=1);stored=next(m for m in metrics if m['topic']==topic);assert np.isclose(np.sqrt(np.mean(err**2)),stored['position_rmse_m']);assert np.isclose(err[-1],stored['last_observed_position_error_m'])
  axes[row,0].plot(x[:,3],x[:,4],label=topic);axes[row,1].plot(x[:,0]-t0,err*100,label=topic);axes[row,2].plot(x[:,0]-t0,np.degrees(x[:,6]-x[:,5]),label=topic)
 for ax,title,xlabel,ylabel in zip(axes[row],['Trajectory','Position error','Yaw error'],['X (m)','Time (s)','Time (s)'],['Y (m)','Error (cm)','Error (deg)']):ax.set(title=en+' — '+title,xlabel=xlabel,ylabel=ylabel);ax.grid(alpha=.25);ax.legend(fontsize=7)
 axes[row,1].set_ylim(0,22);axes[row,2].set_ylim(-5,5)
 details+=['',f'## {label} — {p.name}',f"완료 상태: {test['status']}. 카메라 프레임 상태: {dict(Counter(x['reason'] for x in frames))}. 평가 샘플 {len(d)}개. 마지막 GT부터 명령 로그 종료까지 {events[-1]['t']-d[-1,0]:.3f}초.",f"ZUPT 확인 지연 {min(m['stationary_delay_s'] for m in a['motions']):.2f}–{max(m['stationary_delay_s'] for m in a['motions']):.2f}초. 동시 직진·회전 명령 {a['command_curve_samples']}개. ZUPT 중 encoder vx 최대 {a['max_encoder_speed_while_zero']:.4f} m/s.",f"Monitor 샘플 수(지속시간 비율 아님): {dict(Counter(s['state'] for s in states))}. acceleration_valid=True {sum(s['acceleration_valid'] for s in states)}개: 이번 로그에서는 longitudinal acceleration inconsistency가 유효하지 않았다.",'|동작|목표(m/°)|GT 직진 투영(m) 또는 yaw(°)|DR 정지 전후 변위(m) 또는 yaw(°)|이동 벡터 불일치(cm)|','|---|---:|---:|---:|---:|']
 segment=[]
 for i,(m,e) in enumerate(zip(a['motions'],moves)):
  end=moves[i+1]['t'] if i+1<len(moves) else events[-1]['t'];before=d[(d[:,0]>=e['t']-1)&(d[:,0]<=e['t']-.1)];after=d[(d[:,0]>=end-1)&(d[:,0]<=end-.1)]
  # Independent stop-window median check; no interpolation over camera gaps.
  if min(len(before),len(after))<3:continue
  b=np.median(before,axis=0);z=np.median(after,axis=0);delta=(z[3:5]-b[3:5])-(z[1:3]-b[1:3]);norm=float(np.linalg.norm(delta));segment.append(dict(index=i+1,kind=m['kind'],vector_mismatch_m=norm,delta_xy_m=delta.tolist()))
  turn=m['kind']=='turn';g=m['gt_yaw_change_deg'] if turn else m['gt_forward_projection_m'];pred=m['/localization/dr']['yaw_change_deg' if turn else 'displacement_m'];details.append(f"|{i+1} {'회전' if turn else '직진'}|{m['target']}|{g:.3f}|{pred:.3f}|{norm*100:.2f}|")
 details.append(f'[원본 비교 보고서](../{p.name}/report.html) · [구간 감사 JSON](../{p.name}/primitive_audit.json)')
 all_data.append(dict(trial=p.name,label=label,metrics=metrics,segments=segment))
fig.savefig(out/'terrain_comparison.png',dpi=135);plt.close(fig)
report+=['','![비교 그래프](terrain_comparison.png)','','거친 험지의 새 DR 마지막 차이는 18.66 cm, 준험지는 6.32 cm. 기존 EKF와 거의 같은 결과이며 정확도 개선 증거는 없다. 거친 험지의 4·6번(60° 회전) 이동 벡터 불일치는 약 9.18·11.46 cm다. 이는 오차가 생긴 구간을 나타내며 개별 값의 합이 최종 오차는 아니다. 준험지도 구간 오차의 상쇄가 있어 마지막 오차만 보면 성능을 과대평가할 수 있다.','ZUPT는 정지 후 출력을 고정했지만 이미 누적된 위치 오차를 되돌리지 않았다. CONTACT_LOSS_SUSPECT는 거친 험지에서 40개 샘플이며 실제 접촉 상실의 확정 라벨이 아니다. 평지에도 DEGRADED가 있어 상태명 자체로 slip 검출 정확도를 주장할 수 없다.','태그 미검출은 두 험지 시험 모두 0건이나 프레임 간 최대 간격은 거친 험지 0.402초, 준험지 0.340초다. RMSE는 관측 프레임에 대한 평균이며 시간 가중 평균이 아니다. 시간 offset 전후 변화는 각각 −6.08 ms, +1.38 ms이고 카메라 노출 지연은 미보정이다.','GT 좌표계는 첫 태그 자세를 기준으로 한다. 첫 자세의 기울기, 태그와 base_link 중심 차이, 카메라 pose 오차가 험지 비교에 영향을 줄 수 있다. 회전 중 불일치를 전부 lateral slip이라고 단정할 수 없다. Encoder yaw는 unwrap한 누적 차이다. ToF correction은 본 시험에 없다.']+details
(out/'report.md').write_text('\n\n'.join(report));(out/'summary.json').write_text(json.dumps(all_data,ensure_ascii=False,indent=2));print(out/'report.md')
