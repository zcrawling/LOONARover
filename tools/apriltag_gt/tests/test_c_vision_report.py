"""End-to-end report fixture, no SSH/camera/motion."""
import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from rosbags.rosbag2 import Writer
from rosbags.typesys import get_typestore,Stores

class CReportTest(unittest.TestCase):
 def test_known_scale(self):
  self.run_fixture(False)

 def test_with_tof_fallback(self):
  self.run_fixture(True)

 def run_fixture(self, tof):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root);(p/'camera').mkdir();(p/'rover/estimate').mkdir(parents=True)
   clock=lambda t:dict(best=dict(local_epoch=t,offset_s=0.))
   (p/'test.json').write_text(json.dumps(dict(clock_before=clock(100),clock_after=clock(111))))
   (p/'camera/capture.json').write_text(json.dumps(dict(forward_axis='x',time_offset_s=0)))
   store=get_typestore(Stores.ROS2_HUMBLE);T=lambda name:store.types[name]
   samples=[];windows=[dict(kind='acceleration',rows=[],C_raw=.7,reason='ok'),dict(kind='deceleration',rows=[],C_raw=.7,reason='ok')]
   fields=['t','valid','reprojection_px','x','y','z']+[f'r{i}{j}' for i in range(3) for j in range(3)]
   distance=0.;old=0.
   with Writer(p/'rover/bag',version=9) as bag,(p/'camera/frames.csv').open('w') as f:
    connections=[bag.add_connection(topic,'nav_msgs/msg/Odometry',typestore=store) for topic in ['/wheel/odom','/odometry/filtered','/localization/dr']]
    if tof:
     connections.append(bag.add_connection('/odom_tof_test','nav_msgs/msg/Odometry',typestore=store))
     qc=bag.add_connection('/localization/registration','std_msgs/msg/String',typestore=store)
     for t,reason in [(100,'anchor_initialized'),(110,'insufficient_correspondences')]:
      bag.write(qc,int(t*1e9),store.serialize_cdr(T('std_msgs/msg/String')(json.dumps(dict(accepted=False,reason=reason))),'std_msgs/msg/String'))
    state_conn=bag.add_connection('/localization/state','std_msgs/msg/String',typestore=store)
    w=csv.writer(f);w.writerow(fields)
    for k in range(501):
     s=k*.02;t=100+s;v=.05*s if s<=4 else .2 if s<=6 else .05*(10-s)
     distance+=(old+v)*.01 if k else 0.;old=v
     phase='ACCEL' if s<4 else 'CRUISE' if s<6 else 'DECEL'
     w.writerow([t,1,.1,.7*distance,0.,1.,*np.eye(3).ravel()])
     h=T('std_msgs/msg/Header')(T('builtin_interfaces/msg/Time')(100+k//50,(k%50)*20000000),'odom')
     pos=T('geometry_msgs/msg/Point')(distance,0.,0.);q=T('geometry_msgs/msg/Quaternion')(0.,0.,0.,1.);pose=T('geometry_msgs/msg/PoseWithCovariance')(T('geometry_msgs/msg/Pose')(pos,q),np.zeros(36))
     z=T('geometry_msgs/msg/Vector3')(0.,0.,0.);twist=T('geometry_msgs/msg/TwistWithCovariance')(T('geometry_msgs/msg/Twist')(z,z),np.zeros(36));m=T('nav_msgs/msg/Odometry')(h,'base_link',pose,twist)
     for c in connections:bag.write(c,int(t*1e9),store.serialize_cdr(m,'nav_msgs/msg/Odometry'))
     state=dict(t=t,stationary=False,zero_update=False,bias=[0,0,0],encoder_vx=v,vx=v)
     bag.write(state_conn,int(t*1e9),store.serialize_cdr(T('std_msgs/msg/String')(json.dumps(state)),'std_msgs/msg/String'))
     samples.append(dict(t=t,x=.7*distance,y=0,yaw=0,vx_encoder=v,vx_corrected=.7*v,phase=phase,C_acc=.7,C_dec=.7,C_valid=True,C_unreliable=False,acceleration_mode='linear'))
     for i,include in enumerate([s<=4,s>=6]):
      if include:windows[i]['rows'].append(dict(t=t,vx_encoder=v,v_imu=.7*v,a_corrected=.035 if i==0 else -.035))
   with (p/'rover/estimate/samples.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(samples[0]));w.writeheader();w.writerows(samples)
   (p/'rover/estimate/windows.jsonl').write_text('\n'.join(json.dumps(r) for r in windows))
   subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'compare_c_test.py'),str(p)],check=True,stdout=subprocess.DEVNULL)
   result=json.loads((p/'c_comparison.json').read_text())
   for r in result['windows']:self.assertAlmostEqual(r['C_GT'],.7,places=6);self.assertLess(r['absolute_error'],1e-6)
   metrics=json.loads((p/'evaluation/evaluation.json').read_text());self.assertLess(metrics['odom_c_test']['rmse_m'],1e-6)
   self.assertAlmostEqual(metrics['baselines']['/localization/dr']['last_m'],.36,places=5)
   if tof:
    self.assertAlmostEqual(metrics['baselines']['/odom_tof_test']['last_m'],.36,places=5)
    icp=json.loads((p/'icp_summary.json').read_text());self.assertEqual(icp['accepted'],0);self.assertEqual(len(icp['attempts']),2)
   self.assertTrue((p/'report.html').exists());self.assertTrue((p/'c_comparison.png').exists())

if __name__=='__main__':unittest.main()
