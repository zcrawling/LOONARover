"""Offline FFT ablation, no GT fit and no runtime modifications.
Full-record FFT is noncausal; removal of low frequencies is NOT identified bias.
"""
from pathlib import Path
import json,csv,importlib.util
import numpy as np
from scipy.integrate import cumulative_trapezoid as integ
from rosbags.highlevel import AnyReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('rigid',Path(__file__).with_name('recompute_c_rigid_body.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
OUT=ROOT/'data/apriltag_gt/fft_bias_20261014';OUT.mkdir(exist_ok=True)
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
 def highpass(x,fc):
  spectrum=np.fft.rfft(x);spectrum[freq<=fc]=0
  return np.fft.irfft(spectrum,n=len(x))
 tc,c1,c2,se,valid=mod.coeff(t,v,old);cg=np.full(len(tc),np.nan)
 grows=[x for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/c_test/v1'];g=np.array([[float(x['t_ros']),-float(x['gt_y'])] for x in grows])
 def gi(x):
  k=np.searchsorted(g[:,0],x)
  return np.interp(x,g[:,0],g[:,1]) if 0<k<len(g) and g[k,0]-g[k-1,0]<=.25 else np.nan
 ds=np.array([gi(x) for x in tc])-gi(tc[0]);np.divide(ds,se,out=cg,where=se>0);cg[~valid]=np.nan
 result={'trial':name,'method':'Scalar forward integration; isolate FFT effect, no new lever-arm/rotation combination. Exact original acceleration-window times and C cutoff retained.', 'record_s':len(grid)*dt,'frequency_resolution_hz':float(freq[1]),'frozen_bias':bias,'C_GT_assumed_minus_y':float(cg[-1]),'variants':[]}
 curves={'기존':(c1,c2)};filtered={}
 for label,fc in [('무필터 검증',None),('DC만 제거',0.),('≤0.10 Hz 제거',.1),('≤0.20 Hz 제거',.2),('≤0.50 Hz 제거',.5)]:
  aa=sig if fc is None else highpass(sig,fc)
  # IMU acceleration sampled at matched IMU stamps, integration uses original wheel timestamps as original code.
  wa=a-np.interp(q,grid,sig-aa);vi=integ(wa,t,initial=0);_,c1,c2,_,_=mod.coeff(t,v,vi)
  ia=ideal if fc is None else highpass(ideal,fc);ivi=integ(np.interp(t,grid,ia),t,initial=0);_,ic1,ic2,_,_=mod.coeff(t,v,ivi)
  result['variants'].append({'label':label,'cutoff_hz':fc,'C1':float(c1[-1]),'C2':float(c2[-1]),'error1':float(c1[-1]-cg[-1]),'error2':float(c2[-1]-cg[-1]),'ideal_encoder_control_C1':float(ic1[-1]),'ideal_encoder_control_C2':float(ic2[-1]),'removed_bins':[] if fc is None else freq[freq<=fc].tolist()})
  curves[label]=(c1,c2);filtered[label]=aa
 result['baseline']={'C1':float(curves['기존'][0][-1]),'C2':float(curves['기존'][1][-1])}
 allres.append(result)
 plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False})
 fig,axes=plt.subplots(2,1,figsize=(11,8),sharex=True,layout='constrained')
 for label,(c1,c2) in curves.items():
  if label=='무필터 검증':continue
  axes[0].plot(tc-start,c1,label=label);axes[1].plot(tc-start,c2,label=label)
 for ax in axes:ax.plot(tc-start,cg,'k--',label='C_GT (-Y 가정)');ax.grid(alpha=.2);ax.legend(ncol=2)
 axes[0].set_ylabel('C1');axes[1].set_ylabel('C2');axes[1].set_xlabel('가속 시작 후 시간 (s)');fig.suptitle(f'시험 {n} | FFT 저주파 제거 민감도 (bias 분리 검증 아님)')
 fig.savefig(OUT/f'trial_{n}.png',dpi=150,bbox_inches='tight');plt.close(fig)
 with (OUT/f'trial_{n}_coefficients.csv').open('w') as f:
  wr=csv.writer(f);wr.writerow(['time_s','C_GT']+[label+'_'+c for label in curves for c in ['C1','C2']]);wr.writerows(zip(tc-start,cg,*[x for cs in curves.values() for x in cs]))
 np.savez(OUT/f'trial_{n}_signals.npz',time=grid-start,accel=sig,encoder_ideal_accel=ideal,frequency=freq,**{f'filtered_{i}':x for i,x in enumerate(filtered.values())})
(OUT/'summary.json').write_text(json.dumps(allres,ensure_ascii=False,indent=2))
html=['<!doctype html><meta charset="utf-8"><title>FFT bias 제거 검토</title><style>body{font-family:sans-serif;max-width:1100px;margin:35px auto;line-height:1.6}td,th{padding:7px;border:1px solid #ccc}table{border-collapse:collapse}img{max-width:100%}</style><h1>기존 두 시험: FFT 저주파 제거 재계산</h1><p>출발 정지 bias를 뺀 전방 LIA에 전체 기록 FFT를 적용. DC 또는 지정 저주파 bin을 0으로 만든 뒤 역변환. 원본 스칼라 적분과 비교하여 FFT 효과만 분리. 3축 회전/위치 보정과 조합하지 않음. GT는 평가용 -Y 가정으로만 사용. FFT용으로만 50Hz 선형 재표본화하고, 추정된 저주파 성분을 원래 가속도 샘플에서 차감. 원래 IMU-encoder pairing 및 가속구간 유지. C 계산 초기 0.5초 제외; v 적분은 출발부터.</p><p>이는 전체 기록/미래 정지 구간을 쓰는 비인과 offline 필터이며, FFT의 주기 경계 및 기록 길이에 의존한다. 제거한 저주파가 실제 bias라는 보장은 없다. 문턱값은 GT 최적화 없이 고정된 ablation이다.</p>']
for n,r in enumerate(allres,1):
 html.append(f'<h2>시험 {n}</h2><p>주파수 간격 {r["frequency_resolution_hz"]:.4f} Hz, 기준 C1/C2 {r["baseline"]["C1"]:.4f}/{r["baseline"]["C2"]:.4f}, GT {r["C_GT_assumed_minus_y"]:.4f}</p><table><tr><th>필터</th><th>C1</th><th>C2</th><th>이상적 C=1 대조 C1</th><th>대조 C2</th></tr>')
 for v in r['variants']:html.append(f'<tr><td>{v["label"]}</td><td>{v["C1"]:.4f}</td><td>{v["C2"]:.4f}</td><td>{v["ideal_encoder_control_C1"]:.4f}</td><td>{v["ideal_encoder_control_C2"]:.4f}</td></tr>')
 html.append(f'</table><img src="trial_{n}.png">')
html.append('<p>대조 실험은 실제 encoder 속도를 미분한 이상적 가속도(C=1, bias=0)에 같은 필터를 적용했다. 그 C까지 변하면 필터가 실제 운동을 제거한다는 증거다. 무필터 계산은 원본 가속도 샘플 그대로 사용해 baseline 재현을 확인한다. 정지 전후 평균 차이를 주행 중 정확한 bias 변화로 간주하지 않는다.</p><a href="summary.json">전체 수치</a>')
(OUT/'report.html').write_text(''.join(html))
print(json.dumps(allres,ensure_ascii=False,indent=2))
