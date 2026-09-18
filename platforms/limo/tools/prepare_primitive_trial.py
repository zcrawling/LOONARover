"""Ensure the existing sensor/EKF stack is present. Never publish motion commands."""
import os,subprocess,time
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry


def main():
 rclpy.init();node=rclpy.create_node('loonar_primitive_preflight');received={};child=None
 topics={'/imu':Imu,'/wheel/odom':Odometry,'/odometry/filtered':Odometry}
 subscriptions=[]
 for topic,kind in topics.items():
  subscriptions.append(node.create_subscription(kind,topic,lambda m,t=topic:received.update({t:time.monotonic()}),qos_profile_sensor_data))
 try:
  until=time.monotonic()+2
  while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.05)
  names=node.get_node_names();required=['limo_base_node','loonar_limo_wheel_odometer','ekf_filter_node']
  for name in required:
   if names.count(name)>1:raise RuntimeError('Duplicate node: '+name)
  if not all(name in names for name in required):
   if any(name in names for name in required):raise RuntimeError('Partially running stack: '+str(names)+'; refusing duplicate driver launch')
   # A process in another ROS domain must not be duplicated against the same serial port.
   processes=subprocess.run(['ps','-eo','args'],capture_output=True,text=True,check=True).stdout.splitlines()
   active=[line for line in processes if any('/lib/'+p+'/' in line for p in ['limo_base','robot_localization','loonar_limo_encoder_odom'])]
   if active:raise RuntimeError('ROS processes exist but are not visible in this domain: '+str(active))
   if not os.access('/dev/ttylimo',os.R_OK|os.W_OK):raise RuntimeError('/dev/ttylimo missing or inaccessible')
   print('Starting existing LIMO sensor + wheel odom + EKF stack (no motion).',flush=True)
   with open('/tmp/loonar-localization.log','a') as log:
    child=subprocess.Popen(['ros2','launch','loonar_limo_localization','limo_imu_velocity_ekf.launch.py','port_name:=ttylimo'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  until=time.monotonic()+20
  while time.monotonic()<until:
   rclpy.spin_once(node,timeout_sec=.05);now=time.monotonic()
   if all(now-received.get(t,float('-inf'))<.5 for t in topics):
    print('READY: fresh /imu, /wheel/odom, /odometry/filtered',flush=True);return
   if child and child.poll() is not None:break
  missing=[t for t in topics if time.monotonic()-received.get(t,float('-inf'))>=.5]
  tail=''
  try:tail=open('/tmp/loonar-localization.log').read()[-2500:]
  except OSError:pass
  raise RuntimeError('Missing/stale topics: '+str(missing)+'\n'+tail)
 finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
