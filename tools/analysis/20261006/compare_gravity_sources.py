"""Offline controlled gravity-source comparison. No GT estimator input."""
from pathlib import Path
import json,csv,importlib.util
import numpy as np
from scipy.integrate import cumulative_trapezoid as integ
from rosbags.highlevel import AnyReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('rigid',Path(__file__).with_name('recompute_c_rigid_body.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=ROOT/'data/apriltag_gt/gravity_comparison_20261014';OUT.mkdir(exist_ok=True)
previous=json.loads((ROOT/'data/apriltag_gt/rigid_body_c_20261006/summary.json').read_text());results=[]
for num,name in enumerate(m.TRIALS,1):
 p=ROOT/'data/apriltag_gt'/name;rows=list(csv.DictReader((p/'rover/estimate/samples.csv').open()));lookup={float(x['t']):x for x in rows}
 win=next(json.loads(s) for s in (p/'rover/estimate/windows.jsonl').read_text().splitlines() if json.loads(s)['kind']=='acceleration');t=np.array([x['t'] for x in win['rows']]);v=np.array([x['vx_encoder'] for x in win['rows']]);start=t[0]
 all_t=np.array([float(x['t']) for x in rows]);end=np.searchsorted(all_t,start)-1;begin=max(0,np.searchsorted(all_t,all_t[end]-1,side='right')-1);pre=rows[begin:end+1]
 data={k:{} for k in ['/imu/accel','/imu/gravity','/imu/linear']}
 with AnyReader([p/'rover/bag']) as reader:
  for c,bt,raw in reader.messages(connections=[c for c in reader.connections if c.topic in data]):
   x=reader.deserialize(raw,c.msgtype);stamp=x.header.stamp.sec+x.header.stamp.nanosec/1e9;vec=x.vector if c.topic=='/imu/gravity' else x.linear_acceleration
   data[c.topic][stamp]=[-vec.y,vec.x,vec.z]
 def match(topic,q):
  nt=np.array(sorted(data[topic]));values=np.array([data[topic][x] for x in nt]);idx=np.searchsorted(nt,q);idx=np.clip(idx,1,len(nt)-1);idx=np.where(abs(nt[idx-1]-q)<abs(nt[idx]-q),idx-1,idx);assert max(abs(nt[idx]-q))<1e-5;return values[idx]
 q=np.array([tt+float(lookup[tt]['imu_header_delta_s']) for tt in t]);pq=np.array([float(x['t'])+float(x['imu_header_delta_s']) for x in pre])
 raw=match('/imu/accel',q);grav=match('/imu/gravity',q);lin=match('/imu/linear',q)
 raw0=match('/imu/accel',pq).mean(axis=0);g0=match('/imu/gravity',pq).mean(axis=0);braw=raw0-g0;blin=match('/imu/linear',pq).mean(axis=0)
 saved=np.load(ROOT/f'data/apriltag_gt/rigid_body_c_20261006/trial_{num}_integration.npz');R=saved['rotation'];arot=saved['rotation_acceleration']
 assert np.allclose(saved['time'],t-start) and np.max(abs(saved['acc_base']-(lin-blin)))<1e-7
 propagated=np.einsum('nji,j->ni',R,g0)
 variants={'BNO LIA':lin-blin,'raw-BNO gravity':raw-grav-braw,'raw-gyro gravity':raw-propagated-braw}
 # Initial gravity/bias separation is not identified by one stationary orientation.
 variants['rawmean 초기화 (bias=0 가정)']=raw-np.einsum('nji,j->ni',R,raw0)
 def velocity(acc):return np.einsum('nji,nj->ni',R,integ(np.einsum('nij,nj->ni',R,acc-arot),t,axis=0,initial=0))
 curves={};summary={}
 for label,acc in variants.items():
  vel=velocity(acc);tc,c1,c2,se,valid=m.coeff(t,v,vel[:,0]);curves[label]=(c1,c2)
  summary[label]={'C1':float(c1[-1]),'C2':float(c2[-1]),'v_end':vel[-1].tolist()}
 assert abs(summary['BNO LIA']['C1']-previous[num-1]['variants']['3축 회전+위치']['C1'])<1e-9
 # Difference is exactly the propagated-vs-BNO gravity term, not motion/lever-arm.
 dg=grav-propagated
 vd=np.einsum('nji,nj->ni',R,integ(np.einsum('nij,nj->ni',R,dg),t,axis=0,initial=0))
 assert np.max(abs(velocity(variants['raw-gyro gravity'])-velocity(variants['raw-BNO gravity'])-vd))<1e-10
 _,dc1,dc2,_,_=m.coeff(t,v,vd[:,0])
 result={'trial':name,'initial_gravity_base':g0.tolist(),'raw_bias_base':braw.tolist(),'linear_bias_base':blin.tolist(),'variants':summary,'C_GT_assumed_minus_y':previous[num-1]['C_GT'],
 'gravity_source_delta_C1':float(dc1[-1]),'gravity_source_delta_C2':float(dc2[-1]),'gravity_difference_base_mean_mps2':dg.mean(axis=0).tolist(),'gravity_difference_base_end_mps2':dg[-1].tolist(),
 'notes':'Same gyro-derived R, gyro bias, 0.22s gyro smoothing, CAD lever arm, timestamps and departure bias window as rigid-body comparison. No accel lowpass added. BNO gravity only used to initialize external g0; no later BNO attitude updates. raw bias = raw0-g0 held fixed. Initial split uncertain.'}
 results.append(result)
 plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False})
 fig,ax=plt.subplots(3,1,figsize=(11,10),layout='constrained')
 ax[0].plot(t-start,grav[:,0],label='BNO gravity X');ax[0].plot(t-start,propagated[:,0],label='gyro 전파 gravity X');ax[0].set_ylabel('중력 X (m/s²)')
 for label,(c1,c2) in curves.items():
  ax[1].plot(tc-start,c1,label=label);ax[2].plot(tc-start,c2,label=label)
 ax[1].set_ylabel('C1');ax[2].set_ylabel('C2');ax[2].set_xlabel('가속 시작 후 시간 (s)')
 # GT curve from existing evaluation, no refit.
 gtfile=ROOT/f'data/apriltag_gt/rigid_body_c_20261006/trial_{num}_series.csv';gr=list(csv.DictReader(gtfile.open()));gt=np.array([float(x['C_GT']) for x in gr]);assert len(gt)==len(tc)
 for a in ax[1:]:a.plot(tc-start,gt,'k--',label='C_GT (-Y 가정)')
 for a in ax:a.grid(alpha=.2);a.legend(fontsize=9)
 fig.suptitle(f'시험 {num}: BNO 내부 중력 제거 vs raw + gyro 중력 제거');fig.savefig(OUT/f'trial_{num}.png',dpi=150,bbox_inches='tight');plt.close(fig)
 np.savez(OUT/f'trial_{num}.npz',time=t-start,raw=raw,bno_gravity=grav,gyro_gravity=propagated,gravity_difference=dg,rotation=R)
 with (OUT/f'trial_{num}_C.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['time','C_GT']+[k+'_'+j for k in curves for j in ['C1','C2']]);w.writerows(zip(tc-start,gt,*[x for pair in curves.values() for x in pair]))
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
html=['<!doctype html><meta charset="utf-8"><title>중력 제거 방식 비교</title><style>body{font-family:sans-serif;max-width:1100px;margin:35px auto;line-height:1.6}img{max-width:100%}td,th{border:1px solid #ccc;padding:8px}table{border-collapse:collapse}</style><h1>raw + gyro 중력 제거 비교</h1><p>동일 3축 회전·CAD 장착 위치 보정 조건에서 중력 source만 변경. 추가 가속도 저역통과 없음. 출발 bias window, timestamp pairing, gyro bias 및 0.22초 gyro 평활, 초기 0.5초 C 제외 동일. 기존 LIA 결과 재현 및 두 방식 차이가 중력 차이 적분과 일치함을 assertion 검증.</p><p>g_ext(t)=R(t)^T g0, b_raw=mean(raw_stop)-g0, a_ext=raw-b_raw-g_ext. g0는 출발 정지 BNO gravity 평균으로 초기화; 이후 BNO 자세는 사용하지 않음. 비교용으로 raw 정지 평균 전체를 g0로 취급하고 raw bias=0 가정한 경우도 별도 계산.</p><p>단일 정지 자세로 중력 방향과 raw 가속도 bias를 독립적으로 알 수 없음. gyro drift/scale/축 오차, 초기 중력 오차, 센서 내부 지연 때문에 외부 중력 제거 또한 정답은 아님. GT는 -Y 가정, 평가에만 사용. 차체 회전/센서 위치 보정을 안 한 옛 스칼라 결과와 직접 혼동하지 말 것.</p>']
for i,r in enumerate(results,1):
 html.append(f'<h2>시험 {i}</h2><table><tr><th>방식</th><th>C1</th><th>C2</th></tr>')
 for k,v in r['variants'].items():html.append(f'<tr><td>{k}</td><td>{v["C1"]:.4f}</td><td>{v["C2"]:.4f}</td></tr>')
 html.append(f'</table><p>내부 raw-gravity → gyro 중력 변경에 따른 ΔC1={r["gravity_source_delta_C1"]:+.4f}, ΔC2={r["gravity_source_delta_C2"]:+.4f}. 잠정 GT={r["C_GT_assumed_minus_y"]:.4f}</p><img src="trial_{i}.png">')
html.append('<a href="summary.json">전체 수치</a>');(OUT/'report.html').write_text(''.join(html));print(json.dumps(results,ensure_ascii=False,indent=2))
