import sys,json,numpy as np
from pathlib import Path
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores,get_typestore
from scipy.spatial import cKDTree
from loonar_localization.registration import *
p=Path('data/cubeeye/tof_20260916_183716');q=json.loads((p/'icp_summary.json').read_text());print(q['registration_attempts'][-1]);st=[];cloud=[]
with AnyReader([p/'rover/bag'],default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as bag:
 for c,t,raw in bag.messages(connections=[c for c in bag.connections if c.topic in ['/localization/state','/tof/depth/points']]):
  m=bag.deserialize(raw,c.msgtype)
  if c.topic=='/localization/state':st.append(json.loads(m.data))
  else:
   x=np.frombuffer(m.data,dtype='<f4').reshape(-1,3);cloud.append((m.header.stamp.sec+m.header.stamp.nanosec*1e-9,x@np.array([[0,0,1],[-1,0,0],[0,-1,0]]).T+[.15,0,.033]))
for tag,ts in [('A',next(x['anchor_stamp'] for x in q['registration_attempts'] if x['reason']=='anchor_initialized')),('B',q['registration_attempts'][-1]['stamp'])]:
 t,x=min(cloud,key=lambda r:abs(r[0]-ts));s=min(st,key=lambda r:abs(r['t']-t));globals()[tag]=x;globals()['s'+tag]=s
 print(tag,'n',len(x),'median',np.median(x,axis=0),'xyzlimits',np.quantile(x,[.1,.9],axis=0),'pose',s['pose'])
T=np.linalg.inv(pose_matrix(sA['pose']))@pose_matrix(sB['pose']);print('initial',T)
a=prepare(A,ICPConfig());b=prepare(B,ICPConfig());print('prepared',len(a),len(b))
for sign in [1,0,-1]:
 init=T.copy();init[:3,3]*=sign;dist,ids=cKDTree(a).query(transform(init,b));print('sign',sign,'distance quantiles',np.quantile(dist,[0,.1,.5,.9]),'within15cm',sum(dist<.15));print(register(A,B,init))
np.savez(p/'stop_pair.npz',A=A,B=B,initial=T)
print('stationary frame audit')
for i,(t,x) in enumerate(cloud):
 s=min(st,key=lambda r:abs(r['t']-t))
 if s.get('stationary') and i%4==0:
  z=prepare(x,ICPConfig());print(round(t-cloud[0][0],2),len(z),np.round(np.median(x,axis=0),3))
starts=[(t,x) for t,x in cloud if 1789555043.8<t<1789555047.6]
ends=[(t,x) for t,x in cloud if t>=1789555052.24]
for aa in starts[::max(1,len(starts)//3)]:
 for bb in ends[::max(1,len(ends)//3)]:
  res=register(aa[1],bb[1],T);print('pair',round(aa[0],2),round(bb[0],2),res['accepted'],res['reason'])
