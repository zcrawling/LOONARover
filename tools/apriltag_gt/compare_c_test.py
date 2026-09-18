"""Evaluate a recorded ramp: camera-derived C vs IMU C, no estimator GT input."""
import argparse,csv,html,json,subprocess,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rosbags.highlevel import AnyReader
from rosbags.typesys import get_typestore,Stores
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'common/ros2/loonar_localization'))
from loonar_localization.c_evaluate import bracket_sample


def window_metric(window,gt):
    rows=window['rows'];raw=window.get('C_raw')
    r=dict(window=window['kind'],C_estimate=raw,C_GT=None,absolute_error=None,relative_error_pct=None,
           status='insufficient_window',estimator_reason=window.get('reason'))
    if len(rows)<3:return r
    t=np.array([x['t'] for x in rows]);v=np.array([x['vx_encoder'] for x in rows])
    r.update(start_ros=float(t[0]),end_ros=float(t[-1]))
    if np.any(np.diff(t)<=0) or max(np.diff(t))>.08:r['status']='encoder_gap';return r
    # Regression and vision cover exactly the same saved acceleration/deceleration window.
    a=bracket_sample(t[0],gt,[1,2,3],.25);b=bracket_sample(t[-1],gt,[1,2,3],.25)
    if a is None or b is None:r['status']='missing_GT_endpoint';return r
    ds=float(np.sum(np.diff(t)*(v[1:]+v[:-1])*.5))
    actual=float((b[:2]-a[:2])@np.array([np.cos(a[2]),np.sin(a[2])]))
    if abs(ds)<.01:r['status']='insufficient_distance';return r
    cgt=actual/ds;r.update(C_GT=cgt,encoder_distance_m=ds,vision_distance_m=actual,status='ok')
    if raw is not None:
        r['absolute_error']=abs(raw-cgt)
        r['relative_error_pct']=100*abs(raw-cgt)/abs(cgt) if abs(cgt)>1e-6 else None
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trial',type=Path);args=p.parse_args();out=args.trial
    if not (out/'rover/bag/metadata.yaml').exists():raise ValueError('Recorded bag missing')
    states=[];quality=[];counts={}
    with AnyReader([out/'rover/bag'],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
        counts={topic:sum(c.msgcount for c in bag.connections if c.topic==topic) for topic in {c.topic for c in bag.connections}}
        for c,_,raw in bag.messages(connections=[x for x in bag.connections if x.topic in ['/localization/state','/localization/registration']]):
            r=json.loads(bag.deserialize(raw,c.msgtype).data)
            if c.topic=='/localization/registration':quality.append(r);continue
            if all(k in r for k in ['t','stationary','zero_update','bias','encoder_vx','vx']):states.append(r)
    icp=dict(accepted=sum(bool(r.get('accepted')) for r in quality),attempts=quality,topic_counts=counts)
    (out/'icp_summary.json').write_text(json.dumps(icp,indent=2))
    if not states:raise ValueError('No valid DR diagnostic states recorded')
    (out/'rover/states.jsonl').write_text('\n'.join(json.dumps(x) for x in states))
    (out/'rover/events.jsonl').write_text('')
    subprocess.run([sys.executable,str(ROOT/'tools/apriltag_gt/compare_primitive_test.py'),str(out)],check=True)
    (out/'report.html').replace(out/'baseline_report.html')
    env=__import__('os').environ.copy();env['PYTHONPATH']=str(ROOT/'common/ros2/loonar_localization')
    subprocess.run([sys.executable,'-m','loonar_localization.c_evaluate','--samples',str(out/'rover/estimate/samples.csv'),
                    '--gt-comparison',str(out/'comparison.csv'),'--output',str(out/'evaluation')],env=env,check=True,stdout=subprocess.DEVNULL)
    comparison=list(csv.DictReader((out/'comparison.csv').open()))
    gt=np.array([[float(r[k]) for k in ['t_ros','gt_x','gt_y','gt_yaw']] for r in comparison if r['topic']=='/localization/dr'])
    windows=[json.loads(x) for x in (out/'rover/estimate/windows.jsonl').read_text().splitlines()]
    metrics=[window_metric(w,gt) for w in windows]
    samples=list(csv.DictReader((out/'rover/estimate/samples.csv').open()));last=samples[-1]
    result=dict(windows=metrics,C_acc=last['C_acc'],C_dec=last['C_dec'],C_valid=last['C_valid'],C_unreliable=last['C_unreliable'],
                acceleration_mode=last['acceleration_mode'],definition='C_GT = signed vision forward displacement / integrated encoder vx over the exact saved C window')
    (out/'c_comparison.json').write_text(json.dumps(result,indent=2))
    if metrics:
        keys=list(dict.fromkeys(k for r in metrics for k in r))
        with (out/'c_comparison.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(metrics)
    evaluation=json.loads((out/'evaluation/evaluation.json').read_text())
    pairs=list(csv.DictReader((out/'evaluation/paired.csv').open()))
    fig,axes=plt.subplots(3,1,figsize=(11,11),layout='constrained');t0=gt[0,0]
    x=np.arange(len(metrics));axes[0].bar(x-.18,[r['C_estimate'] if r['C_estimate'] is not None else np.nan for r in metrics],.35,label='IMU C raw')
    axes[0].bar(x+.18,[r['C_GT'] if r['C_GT'] is not None else np.nan for r in metrics],.35,label='Vision C_GT');axes[0].set_xticks(x,[r['window'] for r in metrics]);axes[0].set_ylabel('C (dimensionless)')
    tt=np.array([float(r['t']) for r in samples]);axes[1].plot(tt-t0,[float(r['vx_encoder']) for r in samples],label='Encoder vx')
    axes[1].plot(tt-t0,[float(r['vx_corrected']) for r in samples],label='C-test vx')
    for w in windows:
        if w['rows']:axes[1].plot([r['t']-t0 for r in w['rows']],[r['v_imu'] for r in w['rows']],label='IMU '+w['kind'])
    axes[1].set(xlabel='ROS elapsed (s)',ylabel='Velocity (m/s)')
    axes[2].plot([float(r['t'])-t0 for r in pairs],[float(r['position_error_m'])*100 for r in pairs],'.',label='C-test error vs vision');axes[2].set(xlabel='ROS elapsed (s)',ylabel='Position error (cm)')
    for ax in axes:ax.legend();ax.grid(alpha=.2)
    fig.savefig(out/'c_comparison.png',dpi=130);plt.close(fig)
    def fmt(v):return 'N/A' if v is None else f'{v:.4f}'
    table=''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [r['window'],fmt(r['C_estimate']),fmt(r['C_GT']),fmt(r['absolute_error']),fmt(r['relative_error_pct']),r['status']])+'</tr>' for r in metrics)
    errors=dict(evaluation['baselines']);errors['/odom_c_test']=evaluation['odom_c_test']
    error_table=''.join(f'<tr><td>{html.escape(k)}</td><td>{r["samples"]}</td><td>{100*r["rmse_m"]:.2f}</td><td>{100*r["last_m"]:.2f}</td></tr>' for k,r in errors.items())
    (out/'report.html').write_text('''<!doctype html><meta charset="utf-8"><title>AprilTag / IMU C comparison</title>
<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 16px}table{border-collapse:collapse}td,th{padding:9px;border:1px solid #ccc}img{max-width:100%}p{line-height:1.6}</style>
<h1>AprilTag 기준 C 추정 비교</h1><p>C_GT = 동일 구간 vision 전진 변위 / encoder vx 적분 거리. 가속·감속 C 추정에 사용된 저장 window와 정확히 같은 구간을 비교합니다. GT는 추정기에 입력하지 않습니다.</p>'''+
        f'<p>C_valid={html.escape(last["C_valid"])} / C_unreliable={html.escape(last["C_unreliable"])} / mode={html.escape(last["acceleration_mode"])}</p>'+
        '<table><tr><th>구간</th><th>IMU C</th><th>Vision C_GT</th><th>절대 차이</th><th>상대 차이 %</th><th>GT 상태</th></tr>'+table+'</table>'+
        '<p>C_dec는 최종 정지 이후 역적분한 평가값입니다. C_acc는 가속 종료 이후에만 test odom에 적용됩니다. Raw C는 범위 밖이어도 표시하며 C_valid=false일 때 odom은 encoder로 fallback합니다.</p>'+
        (f'<p>ToF ICP accepted: {icp["accepted"]}. accepted=0이면 ToF odom은 DR fallback이며 보정 성공이 아닙니다. <a href="icp_summary.json">ICP 판정·토픽 기록 수</a></p>' if '/odom_tof_test' in counts else '')+
        '<table><tr><th>Odometry</th><th>비교 샘플</th><th>위치 RMSE cm</th><th>마지막 위치 차이 cm</th></tr>'+error_table+'</table><img src="c_comparison.png">'+
        '<p>static_bias_experiment는 일정 자세 가정입니다. 차체 pitch 변화·시간 지연·카메라 오차가 C에 섞일 수 있습니다. 한 회의 일치는 slip 보정 일반 성능의 입증이 아닙니다. 태그 endpoint가 없으면 C_GT는 N/A이며 누락을 성공으로 채우지 않습니다. C_GT는 직진 투영 거리이고, 경사면 주행거리와 차이가 날 수 있습니다.</p>'+
        '<p><a href="c_comparison.csv">C 비교 CSV</a> · <a href="c_comparison.json">C 비교 JSON</a> · <a href="rover/estimate/samples.csv">센서/추정 CSV</a> · <a href="baseline_report.html">기존 odom 그래프</a> · <a href="evaluation/evaluation.json">구간별 거리·오차</a></p>')
    print('Report:',out/'report.html');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
