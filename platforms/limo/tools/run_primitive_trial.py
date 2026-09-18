"""Explicitly executed motion experiment; packages and driver must already be available."""
import argparse,json,math,signal,subprocess,time,threading,sys
from pathlib import Path
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import Twist
from loonar_localization.core import PrimitiveSequence
from loonar_localization.ros_nodes import DRNode

PLAN=[(0.,.5),(30.,.5),(60.,.2),(60.,.3),(30.,.5)]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--distance',type=float,help='Single straight leg instead of the primitive plan');p.add_argument('--speed',type=float,default=.1);p.add_argument('--tof',action='store_true');p.add_argument('--no-stdin-stop',action='store_true');p.add_argument('--stop-hold',type=float,default=2.);p.add_argument('--angular',type=float,default=.15);p.add_argument('--observe-only-seconds',type=float,help='Record and exercise readiness without publishing any command');p.add_argument('--u-shape',nargs=3,type=float);a=p.parse_args()
 if a.observe_only_seconds is not None and (not math.isfinite(a.observe_only_seconds) or a.observe_only_seconds<=0):p.error('invalid observation duration')
 if not math.isfinite(a.stop_hold) or a.stop_hold<0 or not math.isfinite(a.angular) or a.angular<=0:p.error('invalid hold/angular')
 if not math.isfinite(a.speed) or a.speed<=0 or (a.distance is not None and (not math.isfinite(a.distance) or a.distance<=0)):p.error('positive speed/distance required')
 if a.u_shape and (a.distance is not None or not all(math.isfinite(v) and v>0 for v in a.u_shape)):p.error('u-shape needs positive lengths and cannot combine with distance')
 plan=[(0.,a.distance)] if a.distance is not None else ([(0.,a.u_shape[0]),(90.,a.u_shape[1]),(90.,a.u_shape[2])] if a.u_shape else PLAN)
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False);status={'plan':plan,'speed':a.speed,'angular':a.angular,'stop_hold':a.stop_hold,'status':'preparing'}
 stop=False
 def cancel(*_):
  nonlocal stop;stop=True
 signal.signal(signal.SIGINT,cancel);signal.signal(signal.SIGTERM,cancel)
 def stdin():
  for line in sys.stdin:
   if line.strip()=='STOP':break
  cancel()
 if not a.no_stdin_stop:threading.Thread(target=stdin,daemon=True).start()
 rclpy.init(args=['--ros-args','-p','wheel_position_topic:=/wheel/odometer','-p','wheel_position_names:=[left_wheel_odometer_m, right_wheel_odometer_m]'],signal_handler_options=SignalHandlerOptions.NO)
 dr=DRNode();node=rclpy.create_node('loonar_primitive_trial');ex=SingleThreadedExecutor();ex.add_node(dr);ex.add_node(node)
 # Drain subscriptions continuously; the 20 Hz motion loop must not budget ROS callbacks.
 spin_thread=threading.Thread(target=ex.spin,daemon=True);spin_thread.start()
 pub=node.create_publisher(Twist,'/cmd_vel',10);bag=None;command_sent=False
 events=(out/'events.jsonl').open('w',buffering=1);states=(out/'states.jsonl').open('w',buffering=1);baglog=(out/'bag.log').open('w')
 def publish(v,w,kind,stage):
  nonlocal command_sent
  if a.observe_only_seconds is not None:
   events.write(json.dumps(dict(t=node.get_clock().now().nanoseconds/1e9,kind='OBSERVE_INTENT',stage=stage,vx=v,wz=w))+'\n');return
  command_sent=True
  m=Twist();m.linear.x=float(v);m.angular.z=float(w);pub.publish(m)
  events.write(json.dumps(dict(t=node.get_clock().now().nanoseconds/1e9,monotonic=time.monotonic(),kind=kind,stage=stage,vx=v,wz=w))+'\n')
 try:
  # Readiness is checked before sending any motion. No base-driver bootstrap here.
  deadline=time.monotonic()+10
  while time.monotonic()<deadline and not stop:
   time.sleep(.02)
   if dr.core.last and pub.get_subscription_count()>1 and node.count_publishers('/odometry/filtered')>0:break # includes our own prior subscriber
  if stop:return
  if dr.core.last is None or pub.get_subscription_count()<=1 or node.count_publishers('/odometry/filtered')==0:raise RuntimeError('Preflight failed: '+json.dumps(dict(dr_received=dr.core.last is not None,cmd_subscribers=pub.get_subscription_count(),ekf_publishers=node.count_publishers('/odometry/filtered'),dr_diagnostic=getattr(dr,'last_diagnostic',None),nodes=node.get_node_names())))
  if sum(n=='loonar_dead_reckoning' for n in node.get_node_names())>1:raise RuntimeError('Another shadow DR is running; stop that duplicate before this trial')
  topics=['/imu','/wheel/odometer','/wheel/odom','/odometry/filtered','/tf','/tf_static','/cmd_vel','/localization/dr','/localization/state']
  if a.tof:topics+=['/tof/depth/points','/tof/status','/localization/registration','/odom_tof_test']
  bag=subprocess.Popen(['ros2','bag','record','-o',str(out/'bag'),*topics],stdout=baglog,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+10
  while not stop and time.monotonic()<deadline:
   time.sleep(.02)
   if bag.poll() is not None:raise RuntimeError('rosbag recorder exited')
   if any('rosbag2_recorder' in n for n in node.get_node_names()):break
  else:raise RuntimeError('Recorder did not become ready')
  print('Recording: '+str(out),flush=True)
  status['status']='running';last_t=None;observing_since=time.monotonic();max_age=0.;would_move=False
  for stage,(degrees,distance) in enumerate(plan):
   seq=PrimitiveSequence(normal=a.speed,angular=a.angular,distance_tolerance=.002,yaw_tolerance=math.radians(.5));seq.start(math.radians(degrees),distance)
   settled_since=None;previous=None
   while not stop:
    if a.observe_only_seconds is not None and time.monotonic()-observing_since>=a.observe_only_seconds:break
    r=dr.core.last;now=node.get_clock().now().nanoseconds/1e9
    if r is None or now-r['t']>.25:raise RuntimeError('Sensor feedback unavailable: '+json.dumps(dict(age_s=None if r is None else now-r['t'],diagnostic=getattr(dr,'last_diagnostic',None))))
    max_age=max(max_age,now-r['t'])
    if bag.poll() is not None:raise RuntimeError('Recorder exited during trial')
    if r['t']!=last_t:
     states.write(json.dumps(r)+'\n');last_t=r['t']
    if r['stationary']:
     if settled_since is None:settled_since=r['t']
    else:settled_since=None
    feedback=dict(r,stationary=settled_since is not None and r['t']-settled_since>=a.stop_hold)
    intent=seq.update(feedback)
    key=(intent['primitive'],intent['reason'])
    if key!=previous:
     print(f'Stage {stage+1}/{len(plan)}: {key}',flush=True);previous=key
     events.write(json.dumps(dict(t=now,kind='transition',stage=stage,intent=intent))+'\n')
    would_move=would_move or bool(intent['vx'] or intent['wz'])
    publish(intent['vx'],intent['wz'],intent['primitive'],stage)
    if intent['complete']:break
    time.sleep(.02)
   if stop or a.observe_only_seconds is not None:break
  status.update(status='interrupted' if stop else ('observation_complete' if a.observe_only_seconds is not None else 'complete'),max_feedback_age_s=max_age,ready_for_motion=would_move,command_published=command_sent)
 except Exception as e:
  status.update(status='failed',error=str(e));print(str(e),file=sys.stderr,flush=True)
 finally:
  if command_sent:
   for _ in range(5):publish(0.,0.,'FINAL_STOP',-1);time.sleep(.02)
  if bag and bag.poll() is None:
   bag.send_signal(signal.SIGINT)
   try:bag.wait(timeout=20)
   except subprocess.TimeoutExpired:status['bag_finalize_error']='timeout';bag.terminate()
  (out/'trial.json').write_text(json.dumps(status,indent=2));events.close();states.close();baglog.close()
  ex.shutdown();spin_thread.join(timeout=5);dr.destroy_node();node.destroy_node();rclpy.shutdown()
  print(json.dumps(status),flush=True)
 if status['status'] not in ['complete','observation_complete']:raise SystemExit(1)
if __name__=='__main__':main()
