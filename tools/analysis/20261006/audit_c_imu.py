"""Read-only audit of BNO055 C trials. Does not calibrate from AprilTag or change runtime."""
from pathlib import Path
import csv,json,struct
from collections import defaultdict,Counter
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.signal import savgol_filter
from scipy.spatial.transform import Rotation
from rosbags.highlevel import AnyReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'data/apriltag_gt/imu_audit_20261006';OUT.mkdir(exist_ok=True)
TRIALS=['loonar_c_vision_20261006_162941_311589','loonar_c_vision_20261006_163043_198809']
def stats(x):
 x=np.asarray(x);return {'n':len(x),'mean':np.mean(x,axis=0).tolist(),'std':np.std(x,axis=0).tolist(),'min':np.min(x,axis=0).tolist(),'max':np.max(x,axis=0).tolist()}
def xyz(v):return [v.x,v.y,v.z]
def base(v):return np.asarray(v)@np.array([[0,1,0],[-1,0,0],[0,0,1]])
results=[]
for trial_index,name in enumerate(TRIALS,1):
 p=ROOT/'data/apriltag_gt'/name
 rows=list(csv.DictReader((p/'rover/estimate/samples.csv').open()))
 t=np.array([float(r['t']) for r in rows]);ph=np.array([r['phase'] for r in rows]);a=np.array([float(r['a_corrected']) for r in rows]);bias=np.array([float(r['accel_bias']) if r['accel_bias'] else np.nan for r in rows]);v=np.array([float(r['vx_encoder']) for r in rows]);delta=np.array([float(r['imu_header_delta_s']) for r in rows])
 start=t[ph=='ACCEL'][0];end=t[ph=='DECEL'][-1]
 windows=[json.loads(s) for s in (p/'rover/estimate/windows.jsonl').read_text().splitlines()];win=next(w for w in windows if w['kind']=='acceleration'); frozen=bias[ph=='ACCEL'][0]
 data=defaultdict(dict);cal=defaultdict(Counter);rawmeta=[];tf=[];frames=defaultdict(set)
 with AnyReader([p/'rover/bag']) as reader:
  for c,bt,raw in reader.messages():
   if not (c.topic.startswith('/imu/') or c.topic in ['/tf_static','/mcu/control/raw']):continue
   m=reader.deserialize(raw,c.msgtype)
   if c.topic=='/tf_static':
    for f in m.transforms:tf.append({'parent':f.header.frame_id,'child':f.child_frame_id,'q':xyz(f.transform.rotation)+[f.transform.rotation.w]})
   elif c.topic=='/mcu/control/raw':
    d=json.loads(m.data);b=bytes.fromhex(d['payload'])
    if d['kind']==32:
     cal[str(b[0])][str(b[1])]+=1
     rawmeta.append([d['stamp_ns']/1e9,b[0],struct.unpack_from('<I',b,32)[0],d.get('sync_rtt_ns',0)/1e9])
   else:
    ns=m.header.stamp.sec*10**9+m.header.stamp.nanosec;frames[c.topic].add(m.header.frame_id)
    if c.topic in ['/imu/gravity','/imu/linear_acceleration']:val=xyz(m.vector)
    elif c.topic=='/imu/data':val=xyz(m.angular_velocity)
    elif c.topic=='/imu/orientation_raw':val=xyz(m.orientation)+[m.orientation.w]
    else:val=xyz(m.linear_acceleration)
    data[c.topic][ns]=val
 keys=sorted(set(data['/imu/accel'])&set(data['/imu/gravity'])&set(data['/imu/linear'])&set(data['/imu/linear_acceleration']))
 ti=np.array(keys)/1e9;raw=base([data['/imu/accel'][k] for k in keys]);g=base([data['/imu/gravity'][k] for k in keys]);lin=base([data['/imu/linear'][k] for k in keys]);vec=base([data['/imu/linear_acceleration'][k] for k in keys])
 gyro=np.array([data['/imu/data'].get(k,[np.nan]*3) for k in keys]);gyro=base(gyro)
 query=t+delta;idx=np.searchsorted(ti,query);idx=np.clip(idx,1,len(ti)-1);idx=np.where(abs(ti[idx-1]-query)<abs(ti[idx]-query),idx-1,idx)
 expected=lin[idx,0];used=a+bias;moving=ph!='STOP'
 pre=(ti>=start-2)&(ti<start-.1);post=(ti>=ti[-1]-2);motion=(ti>=start)&(ti<=end)
 out={'trial':name,'tf':tf,'frames':{k:sorted(v) for k,v in frames.items()},'calibration_levels_by_sensor':dict(cal),'reset_counters':sorted(set(x[2] for x in rawmeta)),
 'imu_interval_s':stats(np.diff(ti)),'sync_rtt_s':stats([x[3] for x in rawmeta]),'header_delta_s':stats(delta),'axis_application_error_max_mps2':float(np.nanmax(abs(expected[moving]-used[moving]))),
 'matched_imu_stamp_error_max_s':float(np.max(abs(ti[idx][moving]-query[moving]))),
 'stop_bias_log_note':'STOP row logs bias AFTER update but a_corrected used previous bias; restrict input equality audit to frozen-bias motion.',
 'combined_vector_difference_max_mps2':float(np.max(abs(lin-vec))), 'raw_minus_gravity_minus_linear_mps2':stats(raw-g-lin),'frozen_bias_mps2':float(frozen)}
 for label,mask in [('pre_stop',pre),('post_stop',post),('motion',motion)]:
  out[label]={'linear_base_mps2':stats(lin[mask]),'raw_base_mps2':stats(raw[mask]),'gravity_base_mps2':stats(g[mask]),'gyro_base_radps':stats(gyro[mask]),
             'gravity_tilt_deg':stats(np.degrees(np.arctan2(np.linalg.norm(g[mask,:2],axis=1),g[mask,2])))}
 out['imu_gaps_over_80ms_elapsed_s']=[float(x-start) for x in ti[1:][np.diff(ti)>.08]]
 out['gyro_integral_motion_deg']=np.degrees(np.trapezoid(gyro[motion],ti[motion],axis=0)).tolist()
 # Angular acceleration at nominal sensor lever arm, diagnostic only.
 omega=savgol_filter(gyro,11,2,axis=0);alpha=np.gradient(omega,ti,axis=0);lever=np.array([.03575,0.,-.057]);arot=np.cross(alpha,lever)+np.cross(omega,np.cross(omega,lever))
 amask=(ti>=start)&(ti<=start+2.5)
 out['nominal_lever_arm_accel_forward_mps2']=stats(arot[amask,0])
 predicted_g=g[pre][-1].copy()
 for k in np.flatnonzero(motion)[1:]:predicted_g=Rotation.from_rotvec(-.5*(gyro[k]+gyro[k-1])*(ti[k]-ti[k-1])).apply(predicted_g)
 out['gyro_propagated_final_gravity_base']=predicted_g.tolist()
 out['post_minus_pre_forward_bias_mps2']=float(lin[post,0].mean()-lin[pre,0].mean())
 # Whole motion integration uses frozen departure bias, not post-stop recalibration.
 full=(ti>=start)&(ti<=end+2);it=ti[full];il=lin[full,0]-frozen;iv=cumulative_trapezoid(il,it,initial=0)
 out['integrated_velocity_at_stop_plus_2s_mps']=float(iv[-1])
 w=win['rows'];wt=np.array([r['t'] for r in w]);wv=np.array([r['vx_encoder'] for r in w]);wa=np.array([r['a_corrected'] for r in w]);wi=np.array([r['v_imu'] for r in w])
 out['accel']={'duration_s':float(wt[-1]-wt[0]),'C_acc':win['C_raw'],'encoder_end_mps':float(wv[-1]),'imu_end_mps':float(wi[-1]),'acceleration_mean_mps2':float(wa.mean()),'reintegrate_max_error':float(np.max(abs(cumulative_trapezoid(wa,wt,initial=0)-wi)))}
 out['C_dec']=next(w['C_raw'] for w in windows if w['kind']=='deceleration')
 # Sensitivity only: no tilt is claimed to be actual mounting error.
 sens=[]
 for degrees in [-5,-2,0,2,5]:
  aa=np.cos(np.radians(degrees))*lin[:,0]+np.sin(np.radians(degrees))*lin[:,2]
  bb=float(aa[pre].mean());acc=np.interp(wt,ti,aa)-bb;vel=cumulative_trapezoid(acc,wt,initial=0);mask=abs(wv)>=.02
  sens.append({'pitch_axis_error_deg':degrees,'C_using_pre2s_bias':float(wv[mask]@vel[mask]/(wv[mask]@wv[mask]))})
 out['axis_tilt_sensitivity_not_calibration']=sens
 # Low-frequency lag diagnostic relative to encoder; encoder is not GT.
 u=np.arange(start-.4,end+.4,.02);ev=np.interp(u,t,v);ea=savgol_filter(ev,17,2,deriv=1,delta=.02)
 scores=[]
 for lag in np.arange(-.4,.401,.01):
  la=savgol_filter(np.interp(u+lag,ti,lin[:,0]-frozen),17,2)
  mask=(abs(ea)>.035)&(u>=start)&(u<=end)
  scores.append((float(lag),float(np.corrcoef(ea[mask],la[mask])[0,1]),float(np.sqrt(np.mean((ea[mask]-la[mask])**2)))))
 out['lag_diagnostic']={'positive_means_imu_later':True,'best_correlation':max(scores,key=lambda z:z[1]),'zero':scores[40],'caveat':'Encoder not GT; lag confounded by slip/filter shape; no correction applied.'}
 results.append(out)
 plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False})
 fig,ax=plt.subplots(4,1,figsize=(12,11),sharex=True,layout='constrained')
 for j,l in enumerate(['전방 X','측면 Y','상방 Z']):ax[0].plot(ti-start,lin[:,j],label=l,alpha=.8)
 ax[0].axhline(frozen,color='black',ls='--',label='출발 bias (전방)');ax[0].set_ylabel('linear (m/s²)');ax[0].legend(ncol=4)
 ax[1].plot(ti-start,raw[:,0],label='raw X');ax[1].plot(ti-start,g[:,0],label='gravity X');ax[1].plot(ti-start,lin[:,0],label='linear X');ax[1].set_ylabel('전방 가속도 (m/s²)');ax[1].legend()
 ax[2].plot(u-start,ea,label='encoder 미분 (0.34초 평활)');ax[2].plot(t-start,a,label='추정기 a_corrected',alpha=.6);ax[2].set_ylabel('m/s²');ax[2].legend()
 ax[3].plot(t-start,v,label='encoder vx');ax[3].plot(it-start,iv,label='IMU 적분 (출발 bias 고정)');ax[3].set_ylabel('m/s');ax[3].legend();ax[3].set_xlabel('가속 시작 후 시간 (s)')
 for axes in ax:
  axes.axhline(0,color='gray',ls=':');axes.grid(alpha=.2);axes.set_xlim(-2,ti[-1]-start)
  for phase in ['ACCEL','CRUISE','DECEL']:
   tt=t[ph==phase]-start
   axes.axvspan(tt[0],tt[-1],alpha=.05,color={'ACCEL':'green','CRUISE':'blue','DECEL':'red'}[phase])
 fig.suptitle(f'LOONAR 시험 {trial_index}: 원시 IMU → 모델 입력 검증 (GT 사용 없음)')
 fig.savefig(OUT/f'trial_{trial_index}.png',dpi=150);plt.close(fig)
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))

# Human-readable report; all numerical evidence remains in summary.json.
html=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>LOONAR IMU 입력 감사</title><style>body{font-family:sans-serif;max-width:1100px;margin:35px auto;line-height:1.6}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ccc}img{max-width:100%}</style><h1>LOONAR 두 주행: IMU 측정 및 C 모델 입력 감사</h1>',
'<p>원본 bag 및 estimator 로그만 사용. GT로 bias/축/C를 적합하지 않았으며 운용 코드는 변경하지 않았다.</p>',
'<p>확인: 가속도 calibration 0/3, gyro 3/3, system 0/3가 양 시험 내내 기록됨. 전후 정지의 잔류 선형가속도 영점이 달라짐. 원인으로 센서 고장을 단정할 수 없으며 자세 의존 잔류 오차/내부 중력 추정 및 미교정 상태를 함께 고려해야 한다.</p>',
'<p>입력: base X = -imu Y. 중력 제거된 LIA를 사용하며 이중 중력 제거 없음. 이동 중 a_corrected + frozen_bias와 bag linear의 전방값 차이는 부동소수점 수준. 적분 로그 재현 오차는 0.</p>',
'<table><tr><th>시험</th><th>전 정지 X</th><th>후 정지 X</th><th>변화 m/s²</th><th>중력 기울기 전→후</th><th>C_acc / C_dec (원본 전체 가속)</th></tr>']
for i,r in enumerate(results,1):
 pre=r['pre_stop'];post=r['post_stop']
 html.append(f"<tr><td>{i}</td><td>{pre['linear_base_mps2']['mean'][0]:.4f}</td><td>{post['linear_base_mps2']['mean'][0]:.4f}</td><td>{r['post_minus_pre_forward_bias_mps2']:.4f}</td><td>{pre['gravity_tilt_deg']['mean']:.2f}° → {post['gravity_tilt_deg']['mean']:.2f}°</td><td>{r['accel']['C_acc']:.3f} / {r['C_dec']:.3f}</td></tr>")
html.extend(['</table>', '<p>정지 구간: 가속 시작 전 [-2,-0.1] s 및 bag 마지막 2 s. 전후 encoder≈0 및 gyro 저분산 여부는 원본과 그림으로 교차확인. 기울기는 gravity vector가 의미하는 값이며 장착 오차와 지면/차체 경사를 분리하지 못한다. gyro 적분도 약 11–12° pitch 변화를 보여 고정 장착 오차만으로 설명되지 않는다.</p>',
'<p>모델 한계: 센서 가속도는 장착점의 값이다. 현재 구현은 TF 회전만 사용하며 회전가속도/구심가속도에 의한 lever-arm 항을 제거하지 않는다. 회전하는 body 축에서는 dv_body/dt = a_body − omega × v_body이며 현재 X축 스칼라 적분은 이 항을 모델링하지 않는다. CAD 위치 기반 lever-arm 분석은 위치 미실측 및 gyro 미분/평활 의존성이 있어 크기 진단에 한정한다.</p>',
'<p>시간: header 차이 평균 약 -7 ms. MCU timestamp는 UART 수신 시각이며 센서 내부 필터 지연을 나타내지 않는다. 저주파 encoder 가속도 대비 상관 최대값은 두 시험 약 0.53/0.31, 최적 지연도 불일치한다. 신뢰 가능한 고정 지연을 확정하지 않았다. 첫 시험의 181 ms 데이터 공백은 출발 전이며 가속 구간 공백이 아니다.</p>',
'<p>로그 주의: STOP samples.csv의 a_corrected는 bias 갱신 전 값, accel_bias는 갱신 후 값이므로 해당 행끼리 합치면 입력 복원이 안 되는 구간이 있다. motion 구간에서는 bias가 고정되어 이 문제가 없다. 런타임을 고치지 않고 본 감사에서는 이를 구분했다.</p>',
'<p>판정: C&gt;1을 잘라서 해결할 문제가 아니다. 미교정 상태 확인/보정, 자세 의존 잔류 오차 검증, 회전 중 센서 장착점 효과와 body-frame 속도 모델 보완이 선행되어야 한다. 정지 bias 하나만 빼고 얻은 적분 속도를 독립적인 정답 속도로 취급할 수 없다.</p>',
'<p><a href="https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bno055-ds000.pdf">Bosch BNO055 datasheet §3.6.5.6</a>: LIA의 독립 적분으로 속도/위치를 복원할 때 빠른 오차 누적 가능성을 명시한다.</p>'])
for i in (1,2):html.append(f'<h2>시험 {i}</h2><img src="trial_{i}.png">')
html.append('<p><a href="summary.json">전체 수치 JSON</a></p></html>')
(OUT/'report.html').write_text(''.join(html))
