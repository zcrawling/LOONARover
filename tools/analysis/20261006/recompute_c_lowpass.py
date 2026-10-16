"""Offline low-pass ablation; no GT fitting or runtime changes.
Fourth-order Butterworth forward/backward filtering, DC retained.
"""
from pathlib import Path
import json,csv,importlib.util
import numpy as np
from scipy.integrate import cumulative_trapezoid as integ
from rosbags.highlevel import AnyReader
from scipy.signal import butter, sosfiltfilt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('rigid',Path(__file__).with_name('recompute_c_rigid_body.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
OUT=ROOT/'data/apriltag_gt/lowpass_c_20261014';OUT.mkdir(exist_ok=True)
allres=[]
for n,name in enumerate(mod.TRIALS,1):
 p=ROOT/'data/apriltag_gt'/name
 rows=list(csv.DictReader((p/'rover/estimate/samples.csv').open()));ts=np.array([float(x['t']) for x in rows]);ve=np.array([float(x['vx_encoder']) for x in rows])
 win=next(json.loads(s) for s in (p/'rover/estimate/windows.jsonl').read_text().splitlines() if json.loads(s)['kind']=='acceleration')
 t=np.array([r['t'] for r in win['rows']]);v=np.array([r['vx_encoder'] for r in win['rows']]);a=np.array([r['a_corrected'] for r in win['rows']]);old=np.array([r['v_imu'] for r in win['rows']]);start=t[0];bias=float(next(x['accel_bias'] for x in rows if x['phase']=='ACCEL'))
 lookup={float(x['t']):float(x['imu_header_delta_s']) for x in rows};q=np.array([x+lookup[x] for x in t]);q0=q[0]
 records=[]
 with AnyReader([p/'rover/bag']) as reader:
  for c,bt,raw in reader.messages(connections=[c for c in reader.connections if c.topic=='/imu/linear']):
   m=reader.deserialize(raw,c.msgtype);records.append([m.header.stamp.sec+m.header.stamp.nanosec/1e9,-m.linear_acceleration.y])
 records=np.array(records);dt=.02;grid=np.arange(max(records[0,0],ts[0]),min(records[-1,0],ts[-1]),dt)
 sig=np.interp(grid,records[:,0],records[:,1])-bias
 # Matched encoder-only ideal acceleration supplies a signal-preservation control, not an estimator input.
 enc=np.interp(grid,ts,ve);ideal=np.gradient(enc,dt)
 freq=np.fft.rfftfreq(len(grid),dt)
 def lowpass(x,fc):
  sos=butter(4,fc,fs=1/dt,output='sos')
  return sosfiltfilt(sos,x)
 assert np.max(abs(lowpass(np.ones(len(grid)),2)-1))<1e-10
 tc,c1,c2,se,valid=mod.coeff(t,v,old);cg=np.full(len(tc),np.nan)
 grows=[x for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/c_test/v1'];g=np.array([[float(x['t_ros']),-float(x['gt_y'])] for x in grows])
 def gi(x):
  k=np.searchsorted(g[:,0],x)
  return np.interp(x,g[:,0],g[:,1]) if 0<k<len(g) and g[k,0]-g[k-1,0]<=.25 else np.nan
 ds=np.array([gi(x) for x in tc])-gi(tc[0]);np.divide(ds,se,out=cg,where=se>0);cg[~valid]=np.nan
 result={'trial':name,'method':'Scalar forward integration; 4th-order Butterworth sosfiltfilt (noncausal, squared magnitude response), DC retained, original frozen bias unchanged. Cutoffs fixed at 1,2,5,10Hz, no GT selection. Rotation/lever-arm not combined.', 'record_s':len(grid)*dt,'frequency_resolution_hz':float(freq[1]),'frozen_bias':bias,'C_GT_assumed_minus_y':float(cg[-1]),'variants':[]}
 curves={'기존':(c1,c2)};filtered={}
 for label,fc in [('재표본화만',None),('1 Hz 저역통과',1.),('2 Hz 저역통과',2.),('5 Hz 저역통과',5.),('10 Hz 저역통과',10.)]:
  aa=sig if fc is None else lowpass(sig,fc)
  # IMU acceleration sampled at matched IMU stamps, integration uses original wheel timestamps as original code.
  wa=np.interp(q,grid,aa);vi=integ(wa,t,initial=0);_,c1,c2,_,_=mod.coeff(t,v,vi)
  ia=ideal if fc is None else lowpass(ideal,fc);ivi=integ(np.interp(t,grid,ia),t,initial=0);_,ic1,ic2,_,_=mod.coeff(t,v,ivi)
  result['variants'].append({'label':label,'cutoff_hz':fc,'C1':float(c1[-1]),'C2':float(c2[-1]),'error1':float(c1[-1]-cg[-1]),'error2':float(c2[-1]-cg[-1]),'ideal_encoder_control_C1':float(ic1[-1]),'ideal_encoder_control_C2':float(ic2[-1]),'accel_window_std_mps2':float(np.std(wa))})
  curves[label]=(c1,c2);filtered[label]=aa
 result['baseline']={'C1':float(curves['기존'][0][-1]),'C2':float(curves['기존'][1][-1])}
 allres.append(result)
 plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False})
 fig,axes=plt.subplots(2,1,figsize=(11,8),sharex=True,layout='constrained')
 for label,(c1,c2) in curves.items():
  if label=='재표본화만':continue
  axes[0].plot(tc-start,c1,label=label);axes[1].plot(tc-start,c2,label=label)
 for ax in axes:ax.plot(tc-start,cg,'k--',label='C_GT (-Y 가정)');ax.grid(alpha=.2);ax.legend(ncol=2)
 axes[0].set_ylabel('C1');axes[1].set_ylabel('C2');axes[1].set_xlabel('가속 시작 후 시간 (s)');fig.suptitle(f'시험 {n} | 고주파 제거: 저역통과필터 비교')
 fig.savefig(OUT/f'trial_{n}.png',dpi=150,bbox_inches='tight');plt.close(fig)
 fig,ax=plt.subplots(figsize=(11,4),layout='constrained')
 ax.plot(grid-start,sig,color='gray',alpha=.5,label='필터 전')
 for label in ['2 Hz 저역통과','5 Hz 저역통과']:ax.plot(grid-start,filtered[label],label=label)
 ax.set(xlim=(-.5,t[-1]-start+.5),xlabel='가속 시작 후 시간 (s)',ylabel='전방 가속도 (m/s²)',title=f'시험 {n}: 고주파 저감, 출발 bias 고정')
 ax.grid(alpha=.2);ax.legend();fig.savefig(OUT/f'trial_{n}_accel.png',dpi=150,bbox_inches='tight');plt.close(fig)
 with (OUT/f'trial_{n}_coefficients.csv').open('w') as f:
  wr=csv.writer(f);wr.writerow(['time_s','C_GT']+[label+'_'+c for label in curves for c in ['C1','C2']]);wr.writerows(zip(tc-start,cg,*[x for cs in curves.values() for x in cs]))
 np.savez(OUT/f'trial_{n}_signals.npz',time=grid-start,accel=sig,encoder_ideal_accel=ideal,frequency=freq,**{f'filtered_{i}':x for i,x in enumerate(filtered.values())})
(OUT/'summary.json').write_text(json.dumps(allres,ensure_ascii=False,indent=2))
html=['<!doctype html><meta charset="utf-8"><title>고주파 제거 C 재계산</title><style>body{font-family:sans-serif;max-width:1100px;margin:35px auto;line-height:1.6}td,th{padding:7px;border:1px solid #ccc}table{border-collapse:collapse}img{max-width:100%}</style><h1>고주파 제거 후 C1·C2 재계산</h1><p>기존 전방 스칼라 적분에 4차 Butterworth 저역통과를 추가. 50Hz 재표본화, 전체 기록에 sosfiltfilt 왕복 필터링으로 위상 지연을 없앤 offline 분석. 최종 크기 응답은 단방향 응답의 제곱이며 명목 cutoff에서 약 -6dB. DC 및 출발 bias 보정값 유지, 정지 bias 재적합 없음. 3축 회전/위치 보정과 조합하지 않고 필터 단독 효과를 비교한다.</p><p>가속 시작부터 적분, C는 0.5초 이후 누적 계산. 동일 IMU-encoder pairing 유지. 표의 재표본화만 결과를 통해 보간 효과를 구분한다. 1/2/5/10Hz는 GT로 최적화하지 않았다. C_GT는 이전과 동일한 tag -Y 가정의 평가용 값. 전체 기록/미래 샘플을 사용하므로 실시간 동일 성능을 보장하지 않는다. 출발 경계에서 필터의 선행 응답으로 초기 적분 조건의 오차가 생길 수 있다.</p>']
for n,r in enumerate(allres,1):
 html.append(f'<h2>시험 {n}</h2><p>기존 C1/C2 {r["baseline"]["C1"]:.4f}/{r["baseline"]["C2"]:.4f}, GT {r["C_GT_assumed_minus_y"]:.4f}</p><table><tr><th>필터</th><th>C1</th><th>C2</th><th>이상적 C=1 대조 C1</th><th>대조 C2</th><th>가속도 표준편차</th></tr>')
 for v in r['variants']:html.append(f'<tr><td>{v["label"]}</td><td>{v["C1"]:.4f}</td><td>{v["C2"]:.4f}</td><td>{v["ideal_encoder_control_C1"]:.4f}</td><td>{v["ideal_encoder_control_C2"]:.4f}</td><td>{v["accel_window_std_mps2"]:.4f}</td></tr>')
 html.append(f'</table><img src="trial_{n}.png"><img src="trial_{n}_accel.png">')
html.append('<p>대조: 실제 encoder 속도를 미분한 이상적 가속도(C=1, bias=0)에 같은 필터 적용. 상수 보존 assertion 통과. 고주파 감소가 곧 잔류 bias 제거를 의미하지는 않음.</p><a href="summary.json">전체 수치</a>')
(OUT/'report.html').write_text(''.join(html))
print(json.dumps(allres,ensure_ascii=False,indent=2))
