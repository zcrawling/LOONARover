"""Synthetic full-pose GT/rosbag end-to-end regression, no hardware."""
import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from rosbags.rosbag2 import Writer
from rosbags.typesys import get_typestore,Stores

class ReportTest(unittest.TestCase):
 def test_identical_curved_pose_has_zero_error(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root);(p/'camera').mkdir();(p/'rover').mkdir()
   clock=lambda t:dict(best=dict(local_epoch=t,offset_s=0.))
   (p/'test.json').write_text(json.dumps(dict(clock_before=clock(100),clock_after=clock(103))))
   (p/'camera/capture.json').write_text(json.dumps(dict(forward_axis='x',time_offset_s=0)))
   store=get_typestore(Stores.ROS2_HUMBLE);types=store.types
   T=lambda name:types[name]
   fields=['t','valid','reprojection_px','x','y','z']+[f'r{i}{j}' for i in range(3) for j in range(3)]
   states=[]
   with Writer(p/'rover/bag',version=9) as bag,(p/'camera/frames.csv').open('w') as f:
    connections=[bag.add_connection(topic,'nav_msgs/msg/Odometry',typestore=store) for topic in ['/wheel/odom','/odometry/filtered','/localization/dr']]
    w=csv.writer(f);w.writerow(fields)
    for k in range(101):
     time=100+k*.02;yaw=k*np.pi/100;x=np.sin(yaw);y=1-np.cos(yaw);R=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
     w.writerow([time,1,.1,x,y,1,*R.ravel()])
     h=T('std_msgs/msg/Header')(T('builtin_interfaces/msg/Time')(int(time),int(round((time-int(time))*1e9))),'odom')
     pos=T('geometry_msgs/msg/Point')(x,y,0.);q=T('geometry_msgs/msg/Quaternion')(0.,0.,np.sin(yaw/2),np.cos(yaw/2));pose=T('geometry_msgs/msg/PoseWithCovariance')(T('geometry_msgs/msg/Pose')(pos,q),np.zeros(36))
     z=T('geometry_msgs/msg/Vector3')(0.,0.,0.);twist=T('geometry_msgs/msg/TwistWithCovariance')(T('geometry_msgs/msg/Twist')(z,z),np.zeros(36))
     m=T('nav_msgs/msg/Odometry')(h,'base_link',pose,twist)
     for c in connections:bag.write(c,int(time*1e9),store.serialize_cdr(m,'nav_msgs/msg/Odometry'))
     states.append(dict(t=time,stationary=False,zero_update=False,bias=[0,0,0],encoder_vx=.1,vx=.1))
   (p/'rover/states.jsonl').write_text('\n'.join(json.dumps(r) for r in states));(p/'rover/events.jsonl').write_text('')
   tool=Path(__file__).resolve().parents[1]/'compare_primitive_test.py'
   subprocess.run([sys.executable,str(tool),str(p)],check=True,stdout=subprocess.DEVNULL)
   result=json.loads((p/'comparison.json').read_text())
   self.assertEqual(len(result),3)
   for r in result:
    self.assertLess(r['position_rmse_m'],1e-6)
    self.assertLess(abs(r['last_observed_yaw_error_deg']),1e-6)
   self.assertTrue((p/'report.html').exists())
if __name__=='__main__':unittest.main()
