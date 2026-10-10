"""Offline raw ToF geometry ablation, recorded TF/gravity, unchanged planner.

Compare mount roll hypotheses. No deployment or calibration claim.
"""
from pathlib import Path
from collections import Counter
import json,struct,math
import numpy as np
import cv2
from loonar_recording.journal import Reader
from loonar_fly.avoidance import scene_from_points,Avoidance
from loonar_terrain_core.ros import level_rotation
OUT=Path(__file__).resolve().parent;ROOT=Path('/work/loonar-bags')

def qmatrix(q):
 x,y,z,w=q
 return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def main():
 summaries=[]
 for folder in sorted(ROOT.glob('capture_20261007*')):
  d=json.loads((OUT/(folder.name+'.json')).read_text());start=json.loads((folder/'session.json').read_text())['start_ns']/1e9
  tf={x['child']:x for x in d['tf']};Ropt=qmatrix(tf['tof_optical_frame']['q']);Rmount=qmatrix(tf['tof_link']['q']);offset=np.array(tf['tof_link']['xyz']);Rimu=qmatrix(tf['imu_link']['q'])
  gravity=np.array([[x[0],*x[2:]] for x in d['imu'] if x[1]=='gravity_mps2']);gravity=gravity[np.argsort(gravity[:,0])]
  hypotheses={'current':(0,0),'roll_-90_z+0.05':(-90,.05),'roll_-90_z+0.0915':(-90,.0915),'roll_-90_z+0.12':(-90,.12)}
  states={key:Avoidance() for key in hypotheses}; results={key:[] for key in states}
  reader=Reader(next((folder/'raw').glob('tof-*.journal')));n=0;maps=None
  while (record:=reader.read()) is not None:
   n+=1
   if n%8!=1:continue
   meta,raw=record
   _,w,h,seq,stamp,*cal=struct.unpack('<4IQ12d',raw[:120]);t=stamp/1e9-start
   idx=int(np.argmin(abs(gravity[:,0]-t)))
   if abs(gravity[idx,0]-t)>.06:continue
   level,roll,pitch=level_rotation(Rimu@gravity[idx,1:])
   fx,fy,cx,cy,*dist=cal;K=np.array([[fx,0,cx],[0,fy,cy],[0,0,1.]])
   if maps is None:maps=cv2.initUndistortRectifyMap(K,np.array(dist),np.eye(3),K,(w,h),cv2.CV_32FC1)
   z=np.frombuffer(raw[120:120+w*h*2],dtype='<u2').reshape(h,w).astype('f4')*.001
   amp=np.frombuffer(raw[120+w*h*2:],dtype='<u2').reshape(h,w).astype('f4')
   z[(z<.15)|(z>2.5)]=np.nan
   z=cv2.remap(z,*maps,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=float('nan'))[::4,::4]
   amp=cv2.remap(amp,*maps,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=0)[::4,::4]
   yy,xx=np.mgrid[:h:4,:w:4];valid=np.isfinite(z)&(amp>=30)
   optical=np.stack(((xx-cx)*z/fx,(yy-cy)*z/fy,z),axis=-1)[valid]
   for angle in states:
    rotation_angle,z_shift=hypotheses[angle]
    a=math.radians(rotation_angle);c,s=math.cos(a),math.sin(a);Rx=np.array([[1,0,0],[0,c,-s],[0,s,c]])
    xyz=optical@(Rmount@Rx@Ropt).T+offset+[0,0,z_shift]
    own=(abs(xyz[:,0])<=.15)&(abs(xyz[:,1])<=.15)&(xyz[:,2]>=-.078)&(xyz[:,2]<=.402)
    scene=scene_from_points(xyz[~own]@level.T)
    decision=states[angle].update(scene,t,seq)
    results[angle].append(dict(t=t,ready=scene.get('ready'),floor=scene.get('floor'),center=scene.get('directions',[{}]*4)[3],decision=decision,preferred=scene.get('preferred_heading_rad')))
  reader.close()
  summary=dict(session=folder.name,hypotheses={})
  for angle,rows in results.items():
   good=[x for x in rows if x['ready']]
   summary['hypotheses'][angle]=dict(frames=len(rows),ready=len(good),floor_measured=sum(x['floor']['measured'] for x in good),modes=dict(Counter(x['decision']['mode'] for x in good)),obstacles=dict(Counter(x['center']['obstacle'] for x in good)),floor_height_m=[x['floor']['coefficients'][2] for x in good if x['floor']['measured']])
  (OUT/(folder.name+'_mount.json')).write_text(json.dumps(results,separators=(',',':')))
  summaries.append(summary);print(json.dumps(summary),flush=True)
 (OUT/'mount_summary.json').write_text(json.dumps(summaries,indent=2))
if __name__=='__main__':main()
