"""Offline ICP initial-value/frame sensitivity; never changes live parameters."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
from loonar_localization.registration import register,prepare,pose_matrix,ICPConfig
p=Path(sys.argv[1]);summary=json.loads((p/'icp_summary.json').read_text());quality=summary['registration_attempts'];anchor=next(x for x in quality if x['reason']=='anchor_initialized');last=next(x for x in reversed(quality) if 'anchor_stamp' in x and x['reason']!='anchor_initialized');states=[];clouds=[]
with AnyReader([p/'rover/bag'],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as b:
 for c,_,raw in b.messages(connections=[c for c in b.connections if c.topic in ['/tof/depth/points','/localization/state']]):
  m=b.deserialize(raw,c.msgtype)
  if c.topic=='/localization/state':states.append(json.loads(m.data))
  else:
   x=np.frombuffer(m.data,dtype='<f4').reshape(-1,3);clouds.append((m.header.stamp.sec+m.header.stamp.nanosec*1e-9,x@np.array([[0,0,1],[-1,0,0],[0,-1,0]]).T+[.15,0,.033]))
A=min(clouds,key=lambda x:abs(x[0]-anchor['anchor_stamp']))[1];B=min(clouds,key=lambda x:abs(x[0]-last['stamp']))[1]
a=min(states,key=lambda x:abs(x['t']-anchor['dr_stamp']));b=min(states,key=lambda x:abs(x['t']-last['dr_stamp']));initial=np.linalg.inv(pose_matrix(a['pose']))@pose_matrix(b['pose'])
result=dict(points=[len(A),len(B)],prepared=[len(prepare(A,ICPConfig())),len(prepare(B,ICPConfig()))],initial=initial.tolist(),online=last,sensitivity=[])
for iterations in [40,160]:
 for dx in [0.,.15,float(initial[0,3]),.45,.6]:
  t=initial.copy();t[0,3]=dx;r=register(A,B,t,ICPConfig(iterations=iterations));result['sensitivity'].append(dict(initial_x=dx,iterations=iterations,**r))
  print(iterations,round(dx,3),r['reason'],'xyz',np.round(np.array(r.get('transform',np.eye(4)))[:3,3],4),'rmse',r.get('rmse'))
start=[(t,x) for t,x in clouds if anchor['anchor_stamp']<=t<anchor['anchor_stamp']+3]
end=[(t,x) for t,x in clouds if t>=last['stamp']];result['frame_pairs']=[]
for ai in sorted(set([0,len(start)//2,len(start)-1])):
 for bi in sorted(set([0,len(end)//2,len(end)-1])):
  r=register(start[ai][1],end[bi][1],initial);result['frame_pairs'].append(dict(a_stamp=start[ai][0],b_stamp=end[bi][0],**r))
result['stationary_pairs']=[]
for name,group in [('A',start),('B',end)]:
 for j in [len(group)//2,len(group)-1]:
  r=register(group[0][1],group[j][1],np.eye(4));result['stationary_pairs'].append(dict(stop=name,**r))
print('static checks',[(r['stop'],r['reason'],r.get('rmse'),np.array(r.get('transform',np.eye(4)))[:3,3].tolist()) for r in result['stationary_pairs']])
(p/'icp_audit.json').write_text(json.dumps(result,indent=2));np.savez(p/'stop_pair.npz',A=A,B=B,initial=initial)
print('points',result['points'],result['prepared']);print('frame_pairs',[(r['accepted'],r['reason'],np.array(r.get('transform',np.eye(4)))[:3,3].tolist()) for r in result['frame_pairs']])
