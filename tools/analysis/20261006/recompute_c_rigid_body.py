"""Offline 3-axis C ablation; retains recorded clock matching and baseline.
BNO055 LIA is already gravity-free. No GT enters integration or bias estimation.
"""
from pathlib import Path
import json,csv
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.integrate import cumulative_trapezoid as cumtrap
from scipy.signal import savgol_filter
from rosbags.highlevel import AnyReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'data/apriltag_gt/rigid_body_c_20261006'
TRIALS=['loonar_c_vision_20261006_162941_311589','loonar_c_vision_20261006_163043_198809']

def integrate(t,acc,omega,alpha,r):
    rot=np.empty((len(t),3,3));rot[0]=np.eye(3)
    for k,dt in enumerate(np.diff(t),1):
        rot[k]=rot[k-1]@Rotation.from_rotvec((omega[k-1]+omega[k])*.5*dt).as_matrix()
    rotational=np.cross(alpha,r)+np.cross(omega,np.cross(omega,r))
    aw=np.einsum('nij,nj->ni',rot,acc-rotational)
    vw=cumtrap(aw,t,axis=0,initial=0)
    vb=np.einsum('nji,nj->ni',rot,vw)
    # Independent identity: integrate sensor acceleration, subtract rotational velocity.
    vsw=cumtrap(np.einsum('nij,nj->ni',rot,acc),t,axis=0,initial=0)
    equivalent=vsw-np.einsum('nij,nj->ni',rot,np.cross(omega,r))+np.cross(omega[0],r)
    equiv_body=np.einsum('nji,nj->ni',rot,equivalent)
    return vb,rot,rotational,equiv_body

def coeff(t,v,vi,skip=.5):
    tc=np.r_[t[0]+skip,t[t>t[0]+skip]]
    ev=np.interp(tc,t,v);iv=np.interp(tc,t,vi);den=np.cumsum(ev*ev)
    se=cumtrap(ev,tc,initial=0);si=cumtrap(iv,tc,initial=0)
    c1=np.divide(np.cumsum(ev*iv),den,out=np.full(len(tc),np.nan),where=den>0)
    c2=np.divide(si,se,out=np.full(len(tc),np.nan),where=abs(se)>1e-10)
    valid=(den>=.02)&(se>=.01)&(np.arange(len(tc))>=14)
    c1[~valid]=np.nan;c2[~valid]=np.nan
    return tc,c1,c2,se,valid

def checks():
    t=np.linspace(0,2,2001);w=np.tile([0,.3,0],(len(t),1));al=np.zeros_like(w)
    rot=Rotation.from_rotvec(t[:,None]*w).as_matrix()
    # Independent analytic constant world acceleration under rotating body.
    aw=np.array([.1,.02,-.03]);ab=np.einsum('nji,j->ni',rot,aw)
    vb,_,_,_=integrate(t,ab,w,al,np.zeros(3))
    expect=np.einsum('nji,nj->ni',rot,t[:,None]*aw)
    assert np.max(abs(vb-expect))<1e-10
    # Pure rotation about fixed reference, accelerating angular rate.
    w=t[:,None]*np.array([0,.2,0]);al=np.tile([0,.2,0],(len(t),1));r=np.array([.03,0,-.05])
    acc=np.cross(al,r)+np.cross(w,np.cross(w,r))
    vb,_,_,eq=integrate(t,acc,w,al,r)
    assert np.max(abs(vb))<1e-12 and np.max(abs(eq))<1e-8
    return 'analytic rotating-frame translation and pure angular acceleration: passed'

def main():
    OUT.mkdir(exist_ok=True);check=checks()
    cfg=json.loads((ROOT/'platforms/loonar/ros2/loonar_description/config/cad_mounts.json').read_text())
    frames=json.loads((ROOT/'platforms/loonar/hardware/tf/cad_frames.json').read_text())['frames']
    board=next(x for x in frames if x['frame']=='cad_root_o19063_o19046')
    T=np.array(cfg['cad_to_base'])@np.array(board['root_matrix'])
    # STEP radius-2mm mounting cylinders #776529,531,537,539 at board lower face.
    local=np.array([[x,-1.57,z,1000] for x in [-10.16,10.16] for z in [-8.89,8.89]])/1000
    holes=(T@local.T).T[:,:3];r=holes.mean(axis=0)
    provenance={'cad_sha256':cfg['sha256'],'board_frame':board['frame'],'hole_centres_base_m':holes.tolist(),'imu_position_base_m':r.tolist(),
     'position_note':'User specifies BNO085 mounting hole location. Hole-pattern centre on CAD board lower-face plane used as IMU point. BNO055 chip offset from this plane not measured; +/-5mm sensitivity reported. Not a claim of measured chip centre.',
     'orientation':'retain user-confirmed base X=-IMU Y, base Y=IMU X, base Z=IMU Z; CAD board axes are not substituted for IMU axes.',
     'validation':check}
    (OUT/'geometry.json').write_text(json.dumps(provenance,indent=2))
    summary=[]
    for num,name in enumerate(TRIALS,1):
        p=ROOT/'data/apriltag_gt'/name;rows=list(csv.DictReader((p/'rover/estimate/samples.csv').open()))
        windows=[json.loads(s) for s in (p/'rover/estimate/windows.jsonl').read_text().splitlines()]
        win=next(x for x in windows if x['kind']=='acceleration');wr=win['rows'];t=np.array([x['t'] for x in wr]);v=np.array([x['vx_encoder'] for x in wr]);old=np.array([x['v_imu'] for x in wr])
        lookup={float(x['t']):x for x in rows};all_t=np.array([float(x['t']) for x in rows]);start=t[0]
        data={}
        with AnyReader([p/'rover/bag']) as reader:
            for c,bt,raw in reader.messages(connections=[c for c in reader.connections if c.topic=='/imu/linear']):
                m=reader.deserialize(raw,c.msgtype);ts=m.header.stamp.sec+m.header.stamp.nanosec/1e9
                a=m.linear_acceleration;w=m.angular_velocity
                data[ts]=[-a.y,a.x,a.z,-w.y,w.x,w.z]
        nt=np.array(sorted(data));values=np.array([data[k] for k in nt])
        def match(q):
            idx=np.searchsorted(nt,q);idx=np.clip(idx,1,len(nt)-1);idx=np.where(abs(nt[idx-1]-q)<abs(nt[idx]-q),idx-1,idx)
            assert max(abs(nt[idx]-q))<1e-5
            return values[idx]
        q=np.array([tt+float(lookup[tt]['imu_header_delta_s']) for tt in t]);samples=match(q)
        # Reconstruct core's final stationary rolling bias window, including preceding boundary.
        endidx=np.searchsorted(all_t,start)-1;begin=max(0,np.searchsorted(all_t,all_t[endidx]-1,side='right')-1)
        pre=rows[begin:endidx+1];assert all(x['phase']=='STOP' for x in pre)
        bdata=match(np.array([float(x['t'])+float(x['imu_header_delta_s']) for x in pre]))
        bias=bdata[:,:3].mean(axis=0);gbias=bdata[:,3:].mean(axis=0)
        saved=float(lookup[start]['accel_bias']);assert abs(bias[0]-saved)<1e-7,(bias,saved)
        acc=samples[:,:3]-bias;assert np.max(abs(acc[:,0]-np.array([x['a_corrected'] for x in wr])))<1e-7
        assert np.max(abs(cumtrap(acc[:,0],t,initial=0)-old))<1e-7
        # Offline centred SG smoothing of gyro only, in common recorded wheel-time axis.
        # Preserve the exact recorded IMU/encoder pairing; do not infer hidden sensor latency.
        qt=all_t+np.array([float(x['imu_header_delta_s']) for x in rows]);allw=match(qt)[:,3:]-gbias
        grid=np.arange(start-.4,t[-1]+.4,.02)
        gw=np.column_stack([np.interp(grid,all_t,allw[:,j]) for j in range(3)])
        def run(smooth_s,lever):
            n=max(5,round(smooth_s/.02));n+=1-n%2
            w=savgol_filter(gw,n,2,axis=0);alpha=np.gradient(w,grid,axis=0,edge_order=2)
            ww=np.column_stack([np.interp(t,grid,w[:,j]) for j in range(3)]);aa=np.column_stack([np.interp(t,grid,alpha[:,j]) for j in range(3)])
            return integrate(t,acc,ww,aa,lever)
        full,R,arot,eq=run(.22,r);rot_only,_,_,_=run(.22,np.zeros(3))
        variants={'기존':old,'3축 회전':rot_only[:,0],'3축 회전+위치':full[:,0]}
        tc,_,_,se,valid=coeff(t,v,old)
        # Evaluation only: same provisional tag -Y forward projection as previous report.
        gtrows=[x for x in csv.DictReader((p/'comparison.csv').open()) if x['topic']=='/c_test/v1']
        gt=np.array([[float(x['t_ros']),-float(x['gt_y'])] for x in gtrows])
        def gi(q):
            k=np.searchsorted(gt[:,0],q)
            if k<1 or k>=len(gt) or gt[k,0]-gt[k-1,0]>.25:return np.nan
            return np.interp(q,gt[:,0],gt[:,1])
        ds=np.array([gi(q) for q in tc])-gi(tc[0]);cg=np.divide(ds,se,out=np.full(len(tc),np.nan),where=se>0);cg[~valid]=np.nan
        cs={k:coeff(t,v,x)[1:3] for k,x in variants.items()}
        res={'trial':name,'imu_position_base_m':r.tolist(),'bias_base_mps2':bias.tolist(),'gyro_bias_radps':gbias.tolist(),'bias_samples':len(pre),'bias_interval_s':[float(pre[0]['t'])-start,float(pre[-1]['t'])-start],
         'GT_note':'AprilTag -Y assumption retained, not used by estimator. Projected displacement at tag point, not 3D body path length; tag lever-arm not calibrated.',
         'C_GT':float(cg[-1]),'variants':{k:{'C1':float(z[0][-1]),'C2':float(z[1][-1]),'error_C1':float(z[0][-1]-cg[-1]),'error_C2':float(z[1][-1]-cg[-1])} for k,z in cs.items()},
         'velocity_end_mps':{k:float(x[-1]) for k,x in variants.items()},'velocity_identity_check_max_mps':float(np.max(abs(full-eq))),
         'position_sensitivity':[],'gyro_filter_sensitivity':[]}
        for j in range(3):
            for sign in [-1,1]:
                rr=r.copy();rr[j]+=sign*.005;vv=run(.22,rr)[0][:,0];_,c1,c2,_,_=coeff(t,v,vv)
                res['position_sensitivity'].append({'axis':j,'offset_m':sign*.005,'C1':float(c1[-1]),'C2':float(c2[-1])})
        for smooth in [.10,.22,.34]:
            vv=run(smooth,r)[0][:,0];_,c1,c2,_,_=coeff(t,v,vv);res['gyro_filter_sensitivity'].append({'window_s':smooth,'C1':float(c1[-1]),'C2':float(c2[-1])})
        plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False,'font.size':12})
        fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained')
        for j,(label,color) in enumerate([('C1','#1864ab'),('C2','#d9480f')]):
            curve=cs['3축 회전+위치'][j];prev=cs['기존'][j]
            axes[0].plot(tc-start,curve,color=color,lw=2,label=label);axes[1].plot(tc-start,curve-cg,color=color,lw=2,label=label)
            axes[0].plot(tc-start,prev,color=color,ls=':',alpha=.5,label=label+' 기존');axes[1].plot(tc-start,prev-cg,color=color,ls=':',alpha=.5)
        axes[0].plot(tc-start,cg,color='#343a40',ls='--',label='AprilTag C_GT (-Y 가정)');axes[1].axhline(0,color='gray',ls=':')
        axes[0].set(ylabel='C',title=f'LOONAR 시험 {num} | 3축 회전 + CAD 장착 위치 보정');axes[1].set(ylabel='오차',xlabel='가속 시작 후 시간 (s)')
        for ax in axes:ax.grid(alpha=.2);ax.legend(loc='best');ax.set_xlim(.5,max(2.55,tc[-1]-start))
        fig.suptitle('누적 계산 구간 [0.5초, t]');fig.savefig(OUT/f'trial_{num}.png',dpi=160,bbox_inches='tight');fig.savefig(OUT/f'trial_{num}.svg',bbox_inches='tight');plt.close(fig)
        with (OUT/f'trial_{num}_series.csv').open('w') as f:
            writer=csv.writer(f);writer.writerow(['t_s','C_GT']+[k+'_'+c for k in cs for c in ['C1','C2']]);writer.writerows(zip(tc-start,cg,*[curve for z in cs.values() for curve in z]))
        np.savez(OUT/f'trial_{num}_integration.npz',time=t-start,acc_base=acc,rotation=R,rotation_acceleration=arot,velocity_base=full,velocity_rotation_only=rot_only,velocity_old=old,encoder=v)
        summary.append(res)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    html=['<!doctype html><meta charset="utf-8"><title>3축 회전 및 CAD 위치 보정</title><style>body{font-family:sans-serif;max-width:1100px;margin:40px auto;line-height:1.6}img{width:100%}td,th{padding:8px;border:1px solid #ccc}table{border-collapse:collapse}</style><h1>LOONAR: 3축 회전 + CAD 장착 위치 보정</h1>',
     f'<p>IMU 위치: {r.tolist()} m. BNO085 장착 홀 패턴 중심, CAD 보드 하단 평면. 칩 중심 높이 미실측 ±5mm 민감도 별도. 기존 IMU 축 방향 유지.</p>',
     '<p>출발 전 동일 정지 window로 3축 accel/gyro bias 추정. 기존 전방 bias 및 스칼라 적분이 원본과 일치함을 검증. 중력 제거된 linear acceleration 사용(중력 추가 제거 없음). Gyro SG 0.22초 평활 및 미분, SO(3) 자세 적분, alpha×r 및 omega×(omega×r) 제거 후 고정 좌표계 적분 및 body X 투영. 초기 속도 0. 0.5초 제외는 C 계산에만 적용, 초기 속도 누적 유지. 원본 timestamp pairing 유지, 미확정 센서 내부 지연은 보정하지 않음.</p>',
     '<p>평가 GT는 이전과 동일한 tag -Y 전방 가정. IMU 모델/위치/평활값을 GT에 맞춰 선택하지 않음. 태그의 수평 투영거리와 body 전방 3D 이동거리의 기준 차이, 태그 장착점 회전 영향은 미보정이므로 GT 비교는 잠정적.</p>',
     '<table><tr><th>시험</th><th>모델</th><th>C1</th><th>C2</th><th>C_GT</th><th>오차 C1</th><th>오차 C2</th></tr>']
    for i,res in enumerate(summary,1):
        for label,z in res['variants'].items():html.append(f"<tr><td>{i}</td><td>{label}</td><td>{z['C1']:.4f}</td><td>{z['C2']:.4f}</td><td>{res['C_GT']:.4f}</td><td>{z['error_C1']:+.4f}</td><td>{z['error_C2']:+.4f}</td></tr>")
    html.append('</table><p>센서 calibration 0/3, 자세별 잔류 bias 변화는 이 모델만으로 해결되지 않음. 운용 TF/MCU/V1 및 원본 bag은 변경하지 않음. 각도 가속도 적분과 회전속도 차감의 동등성 검사 및 합성 운동 검증 수행.</p>')
    for i in [1,2]:html.append(f'<h2>시험 {i}</h2><img src="trial_{i}.png">')
    html.append('<a href="summary.json">수치 및 민감도</a> · <a href="geometry.json">CAD 좌표 근거</a>')
    (OUT/'report.html').write_text(''.join(html))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
