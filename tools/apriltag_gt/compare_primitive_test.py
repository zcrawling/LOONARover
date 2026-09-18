"""Evaluate full-pose top-mounted AprilTag against independent ROS odometry."""
import argparse,csv,json,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore


def body_rotation(tag_rotation,axis):
 f=np.array({'x':[1,0,0],'-x':[-1,0,0],'y':[0,1,0],'-y':[0,-1,0]}[axis]);z=np.array([0,0,1])
 return tag_rotation@np.column_stack([f,np.cross(z,f),z])


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('trial',type=Path);a=p.parse_args();out=a.trial
 if not (out/'rover/bag/metadata.yaml').exists():
  p.exit(1,'기록된 rosbag이 없습니다. rover/trial.json 또는 rover.log의 준비 실패 원인을 확인하세요.\n')
 state=json.loads((out/'test.json').read_text());meta=json.loads((out/'camera/capture.json').read_text())
 b=state['clock_before']['best'];e=state['clock_after']['best']
 if abs(e['offset_s']-b['offset_s'])>.1:raise ValueError('Clock changed >100ms; GT comparison not trustworthy')
 gt=[];rot=[]
 for r in csv.DictReader((out/'camera/frames.csv').open()):
  if r['valid']!='1' or not r.get('r00') or float(r['reprojection_px'])>2:continue
  local=float(r['t'])-meta.get('time_offset_s',0);t=local+np.interp(local,[b['local_epoch'],e['local_epoch']],[b['offset_s'],e['offset_s']])
  gt.append([t,float(r['x']),float(r['y']),float(r['z'])]);rot.append(body_rotation(np.array([float(r[f'r{i}{j}']) for i in range(3) for j in range(3)]).reshape(3,3),meta['forward_axis']))
 gt=np.array(gt);rot=np.array(rot)
 if len(gt)>1 and np.any(np.diff(gt[:,0])<=0):raise ValueError('Nonmonotonic GT timestamps')
 if len(gt)<5:raise ValueError('Too few full-pose GT frames')
 topics=['/wheel/odom','/odometry/filtered','/localization/dr'];odom={t:[] for t in topics}
 with AnyReader([out/'rover/bag'],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
  if any(c.topic=='/odom_tof_test' and c.msgcount>0 for c in bag.connections):
   topics.append('/odom_tof_test');odom['/odom_tof_test']=[]
  for c,_,raw in bag.messages(connections=[c for c in bag.connections if c.topic in topics]):
   m=bag.deserialize(raw,c.msgtype);q=m.pose.pose.orientation
   odom[c.topic].append([m.header.stamp.sec+m.header.stamp.nanosec*1e-9,m.pose.pose.position.x,m.pose.pose.position.y,np.arctan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))])
 if any(len(v)<2 for v in odom.values()):raise ValueError('Missing required odometry topics')
 start=max(gt[0,0],*[v[0][0] for v in odom.values()]);i=int(np.searchsorted(gt[:,0],start));
 if i>=len(gt):raise ValueError('GT and odometry have no common interval')
 t0=gt[i,0];origin=gt[i,1:];R0=rot[i]
 gt=gt[i:];rot=rot[i:];pos=(gt[:,1:]-origin)@R0;yaw=np.unwrap([np.arctan2((R0.T@R)[1,0],(R0.T@R)[0,0]) for R in rot])
 fig,ax=plt.subplots(2,2,figsize=(12,9),layout='constrained');t=gt[:,0]-t0
 # Break camera curves at lost-tracking gaps.
 breaks=np.r_[False,np.diff(gt[:,0])>.25];draw=pos.copy();draw[breaks]=np.nan;yy=yaw.copy();yy[breaks]=np.nan
 ax[0,0].plot(draw[:,0],draw[:,1],label='AprilTag GT');ax[0,1].plot(t,np.degrees(yy),label='AprilTag GT')
 summary=[];paired=[]
 for name,raw in odom.items():
  d=np.array(raw);d[:,3]=np.unwrap(d[:,3]);origin=np.array([np.interp(t0,d[:,0],d[:,j]) for j in range(1,4)]);theta=origin[2]
  xy=d[:,1:3]-origin[:2];d[:,1]=xy[:,0]*np.cos(theta)+xy[:,1]*np.sin(theta);d[:,2]=-xy[:,0]*np.sin(theta)+xy[:,1]*np.cos(theta);d[:,3]-=theta
  visible=d[:,0]>=t0;ax[0,0].plot(d[visible,1],d[visible,2],label=name);ax[0,1].plot(d[visible,0]-t0,np.degrees(d[visible,3]),label=name)
  index=np.clip(np.searchsorted(d[:,0],gt[:,0]),1,len(d)-1);good=(gt[:,0]>=d[0,0])&(gt[:,0]<=d[-1,0])&(d[index,0]-d[index-1,0]<.08)
  pred=np.column_stack([np.interp(gt[:,0],d[:,0],d[:,j]) for j in range(1,4)])
  err=np.linalg.norm(pred[:,:2]-pos[:,:2],axis=1);ye=pred[:,2]-yaw
  ax[1,0].plot(t[good],err[good],'.',label=name);ax[1,1].plot(t[good],np.degrees(ye[good]),'.',label=name)
  if good.any():summary.append(dict(topic=name,GT_samples=int(good.sum()),position_rmse_m=float(np.sqrt(np.mean(err[good]**2))),last_observed_position_error_m=float(err[good][-1]),last_observed_yaw_error_deg=float(np.degrees(ye[good][-1])),last_GT_elapsed_s=float(t[good][-1])))
  for k in np.flatnonzero(good):paired.append(dict(topic=name,t_ros=gt[k,0],gt_x=pos[k,0],gt_y=pos[k,1],gt_yaw=yaw[k],odom_x=pred[k,0],odom_y=pred[k,1],odom_yaw=pred[k,2],position_error_m=err[k],yaw_error_rad=ye[k]))
 for aa in ax.ravel():aa.grid(alpha=.2);aa.legend()
 ax[0,0].set(xlabel='X (m)',ylabel='Y (m)',title='Start-aligned trajectories');ax[0,0].axis('equal')
 ax[0,1].set(xlabel='Time (s)',ylabel='Yaw (deg)');ax[1,0].set(xlabel='Time (s)',ylabel='Position error (m)');ax[1,1].set(xlabel='Time (s)',ylabel='Yaw error (deg)')
 fig.savefig(out/'comparison.png',dpi=130);plt.close(fig)
 if not paired:raise ValueError('No valid GT/odom time pairs')
 with (out/'comparison.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
 states=[json.loads(x) for x in (out/'rover/states.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (out/'rover/events.jsonl').read_text().splitlines()]
 fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained');tt=np.array([r['t']-t0 for r in states]);ax[0].step(tt,[r['stationary'] for r in states],label='stationary');ax[0].step(tt,[r['zero_update'] for r in states],label='ZUPT',linestyle='--')
 ax[1].plot(tt,[np.degrees(r['bias'][2]) for r in states],label='gyro bias deg/s');ax[2].plot(tt,[r['encoder_vx'] for r in states],label='encoder vx');ax[2].plot(tt,[r['vx'] for r in states],label='DR vx')
 for aa in ax:aa.grid(alpha=.2);aa.legend()
 ax[-1].set_xlabel('Time (s)');fig.savefig(out/'stationary.png',dpi=120);plt.close(fig)
 (out/'comparison.json').write_text(json.dumps(summary,indent=2))
 (out/'report.html').write_text('<meta charset="utf-8"><style>body{font:16px system-ui;max-width:1200px;margin:30px auto}img{width:100%}</style><h1>Primitive / ZUPT 시험</h1><p>수평 태그의 +Z가 body +Z, 지정 forward-axis가 body +X이며 태그 XY 중심과 base_link XY가 일치한다고 가정. 시작 pose만 정렬, 거리 scale fitting 없음. 카메라 시각은 receipt 시각이므로 exposure 지연이 남음. 누락 구간의 GT를 보간해 채우지 않음. last observed는 전체 시험 종료를 뜻하지 않을 수 있음.</p><img src="comparison.png"><img src="stationary.png"><pre>'+html.escape(json.dumps(summary,indent=2))+'</pre><p><a href="comparison.csv">동기 비교 CSV</a> · 원본 bag, 전체 frame pose, 명령 events와 estimator states 보존.</p>')
 print('Report:',out/'report.html')
if __name__=='__main__':main()
