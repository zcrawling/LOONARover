from pathlib import Path
import json,struct
import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from loonar_recording.journal import Reader
ROOT=Path('/work/loonar-bags');OUT=Path(__file__).resolve().parent
names=['capture_20261007_160348_509053','capture_20261007_161505_274231','capture_20261007_161712_443193']
report=[]
fig,axs=plt.subplots(3,4,figsize=(15,9))
for row,name in enumerate(names):
 folder=ROOT/name;start=json.loads((folder/'session.json').read_text())['start_ns']/1e9
 tof=Reader(next((folder/'raw').glob('tof-*.journal')));frames=[]
 while (record:=tof.read()) is not None:frames.append(record)
 chosen=frames[len(frames)//2];meta,raw=chosen
 magic,w,h,seq,ts,*cal=struct.unpack('<4IQ12d',raw[:120]);z=np.frombuffer(raw[120:120+w*h*2],dtype='<u2').reshape(h,w)*.001
 a=np.frombuffer(raw[120+w*h*2:],dtype='<u2').reshape(h,w)
 target=ts/1e9;cam=Reader(next((folder/'raw').glob('camera-*.journal')));closest=None
 while (record:=cam.read()) is not None:
  m,jpeg=record;t=m['timing']['stamp_ns']/1e9
  if closest is None or abs(t-target)<closest[0]:closest=(abs(t-target),t,jpeg)
  if t>target+1:break
 rgb=cv2.imdecode(np.frombuffer(closest[2],np.uint8),cv2.IMREAD_COLOR)
 axs[row,0].imshow(cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB));axs[row,0].set_title(name.split('_')[2]+' camera +%.1fs'%(closest[1]-start))
 im=axs[row,1].imshow(np.where(z>0,z,np.nan),vmin=0,vmax=1.5,cmap='turbo');axs[row,1].set_title('Raw depth +%.1fs'%(target-start));fig.colorbar(im,ax=axs[row,1],shrink=.7)
 im=axs[row,2].imshow(a,vmin=0,vmax=np.quantile(a,.99),cmap='gray');axs[row,2].set_title('Raw amplitude');fig.colorbar(im,ax=axs[row,2],shrink=.7)
 yy,xx=np.mgrid[:h:4,:w:4];zz=z[::4,::4];valid=np.isfinite(zz)&(zz>=.15)&(zz<=2.5)&(a[::4,::4]>=30)
 fx,fy,cx,cy,*dist=cal
 points=np.stack([zz,-(xx-cx)*zz/fx,-(yy-cy)*zz/fy],axis=-1)[valid]+[.03575,.00005,-.0075]
 axs[row,3].scatter(points[:,0],points[:,2],s=1,alpha=.25);axs[row,3].axhline(-.098,color='green');axs[row,3].axhline(-.098+.0588,color='red',linestyle='--');axs[row,3].set(xlim=(0,1),ylim=(-.4,.4),title='Unrectified side view / nominal floor',xlabel='forward m',ylabel='height from axle m')
 report.append(dict(session=name,w=w,h=h,calibration=cal,depth_quantiles=np.quantile(z[z>0],[.01,.1,.5,.9,.99]).tolist(),amplitude_quantiles=np.quantile(a,[.1,.5,.9,.99]).tolist(),zero_depth_fraction=float((z==0).mean()),point_xyz_quantiles=np.quantile(points,[.05,.5,.95],axis=0).tolist()))
for ax in axs[:,:3].ravel():ax.axis('off')
fig.tight_layout();fig.savefig(OUT/'sensor_contact_sheet.png',dpi=140);plt.close(fig)
(OUT/'frame_summary.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
