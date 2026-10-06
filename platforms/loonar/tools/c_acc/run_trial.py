"""LOONAR ramp C trial. Existing gateway/MCU/ROS bridge must already run.
Default is a stationary preparation test; only --execute sends commands.
"""
import argparse
import csv
import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading
from .profile import cruise_duration, velocity

ROOT=Path(__file__).resolve().parents[4]

def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in [('speed',.25),('ramp',2.5),('cruise',2.),('decel',2.5),('stop',4.)]:
        p.add_argument('--'+k,type=float,default=v)
    p.add_argument('--distance',type=float,help='Nominal command integral in metres; NOT actual distance control')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--stdin-stop',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--output',type=Path)
    p.add_argument('--gatewayctl',default='/opt/loonar/current/bin/vehicle_gatewayctl')
    p.add_argument('--socket',default=str(Path.home()/'loonar-motor-bench/runtime/gateway/cfs.sock'))
    p.add_argument('--imu-time-offset',type=float,default=0.)
    a=p.parse_args()
    try:a.cruise=cruise_duration(a.speed,a.ramp,a.cruise,a.decel,a.stop,a.distance)
    except ValueError as e:p.error(str(e))
    if not math.isfinite(a.imu_time_offset):p.error('finite time offset required')
    return a


def main():
    a=arguments()
    profile={k:getattr(a,k) for k in ['speed','ramp','cruise','decel','stop']}
    profile['nominal_distance']=a.speed*((a.ramp+a.decel)/2+a.cruise)
    print(json.dumps(profile),flush=True)
    if a.dry_run:return
    import rclpy
    from rclpy.node import Node
    from rclpy.time import Time
    from tf2_ros import Buffer,TransformListener
    from geometry_msgs.msg import Twist
    from std_msgs.msg import String
    import numpy as np
    from scipy.spatial.transform import Rotation
    rclpy.init();node=Node('loonar_c_trial')
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    buf=Buffer();listener=TransformListener(buf,node)
    children=[]; logs=[]; command_started=False
    out=a.output or Path.home()/'odom_tests'/datetime.datetime.now().strftime('loonar_c_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    state=dict(status='preparing',platform='LOONAR',profile=profile,acceleration_mode='linear',motion_requested=a.execute,
               imu_time_offset_s=a.imu_time_offset,signal_latency_calibrated=False)
    latest={}
    def diagnostic(m):latest.update(json.loads(m.data))
    sub=node.create_subscription(String,'/c_test/diagnostics',diagnostic,10)
    phase=node.create_publisher(String,'/c_test/phase',10)
    commands=node.create_publisher(Twist,'/c_test/cmd_vel',10)
    def start(cmd,name):
        log=(out/(name+'.log')).open('w');logs.append(log)
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        children.append(child);return child
    def spin(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)
            for child in children:
                if child.poll() is not None:raise RuntimeError('Trial subprocess exited; inspect logs')
    def send(name,v):
        nonlocal command_started
        # Publish actual issue timestamp; GT is never consumed here.
        t=node.get_clock().now().nanoseconds/1e9
        phase.publish(String(data=json.dumps(dict(t=t,phase=name))))
        command_started=True
        subprocess.run([a.gatewayctl,'manual',a.socket,str(v),'0'],check=True,timeout=1.)
        m=Twist();m.linear.x=v;commands.publish(m)
        writer.writerow(dict(t=t,phase=name,vx_command=v,wz_command=0.));command_log.flush()
    command_log=(out/'commands.csv').open('w');writer=csv.DictWriter(command_log,fieldnames=['t','phase','vx_command','wz_command']);writer.writeheader()
    try:
        if a.stdin_stop:
            def cancel_on_input():
                sys.stdin.readline()
                os.kill(os.getpid(),signal.SIGINT)
            threading.Thread(target=cancel_on_input,daemon=True).start()
        spin(1.)
        if any(name in ('loonar_dead_reckoning_c_test','odom_c_test_estimator') for name,_ in node.get_node_names_and_namespaces()):
            raise RuntimeError('A C test is already running')
        if a.execute and (not Path(a.gatewayctl).is_file() or not Path(a.socket).is_socket()):
            raise RuntimeError('Gateway executable/socket not found')
        # Only provide missing IMU mount; never duplicate an existing TF owner.
        config=json.loads((ROOT/'platforms/loonar/ros2/loonar_description/config/cad_mounts.json').read_text())['imu']
        if not buf.can_transform('base_link','imu_link',Time()):
            xyz=config['xyz_m'];rpy=config['rpy_rad']
            start(['ros2','run','tf2_ros','static_transform_publisher','--x',str(xyz[0]),'--y',str(xyz[1]),'--z',str(xyz[2]),
                   '--roll',str(rpy[0]),'--pitch',str(rpy[1]),'--yaw',str(rpy[2]),'--frame-id','base_link','--child-frame-id','imu_link'],'imu_tf')
            state['imu_tf_source']='nominal_CAD_config'
            deadline=time.monotonic()+15
            while not buf.can_transform('base_link','imu_link',Time()) and time.monotonic()<deadline:
                spin(.1)
        tr=buf.lookup_transform('base_link','imu_link',Time()).transform
        q=tr.rotation;R=Rotation.from_quat([q.x,q.y,q.z,q.w]).as_matrix()
        expected=Rotation.from_euler('xyz',config['rpy_rad']).as_matrix()
        if not np.allclose(R,expected,atol=1e-5):raise RuntimeError('Existing IMU TF disagrees with confirmed mounting; not overriding it')
        state['imu_transform']=dict(xyz=[tr.translation.x,tr.translation.y,tr.translation.z],quaternion=[q.x,q.y,q.z,q.w])
        topics=['/imu/data','/imu/accel','/imu/linear_acceleration','/imu/gravity','/imu/linear',
                '/imu/orientation_raw','/mcu/control/raw','/motor/feedback','/wheel/odom','/odometry/filtered',
                '/localization/dr','/localization/state','/c_test/v1','/c_test/state','/odom_c_test',
                '/c_test/phase','/c_test/diagnostics','/c_test/cmd_vel','/tf','/tf_static']
        start(['ros2','bag','record','--storage','sqlite3','-o',str(out/'bag')]+topics,'bag');spin(1.)
        start([sys.executable,'-c','from loonar_localization.ros_nodes import dr_main; dr_main()',
               '--ros-args','-r','__node:=loonar_dead_reckoning_c_test','-r','imu:=/imu/linear',
               '-r','localization/dr:=/c_test/v1','-r','localization/state:=/c_test/state','-r','cmd_vel:=/c_test/cmd_vel',
               '-p','publish_odom_tf:=false','-p','gravity_compensation_validated:=true'], 'v1')
        start([sys.executable,'-m','loonar_localization.c_accel_node','--ros-args',
               '-r','/imu:=/imu/linear','-r','/localization/dr:=/c_test/v1','-r','localization/state:=/c_test/state',
               '-p','acceleration_mode:=linear','-p','imu_time_offset_s:='+str(a.imu_time_offset),
               '-p','output_dir:='+str(out/'estimate')], 'estimator')
        end=time.monotonic()+30
        while time.monotonic()<end:
            spin(.1)
            age=node.get_clock().now().nanoseconds/1e9-latest.get('t',0)
            if latest.get('bias_ready') and latest.get('acceleration_valid') and 0<=age<.2:break
        else:raise RuntimeError('No valid stationary bias within 30s; inspect IMU, wheel and TF logs')
        print('READY: stationary bias + gravity-free acceleration. '+str(out),flush=True)
        if not a.execute:
            spin(2.);state['status']='prepared';return
        start_t=time.monotonic()
        while time.monotonic()-start_t<a.stop:send('STOP',0.);spin(.05)
        start_t=time.monotonic()
        duration=a.ramp+a.cruise+a.decel+a.stop
        while time.monotonic()-start_t<duration:
            name,v=velocity(time.monotonic()-start_t,a.speed,a.ramp,a.cruise,a.decel)
            send(name,v);spin(.05)
        send('STOP',0.);spin(1.)
        state['status']='complete'
    except BaseException as exc:
        state.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc))
        raise
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if command_started:
            try:subprocess.run([a.gatewayctl,'stop',a.socket],check=True,timeout=2.);state['stop_sent']=True
            except Exception as exc:state.update(status='stop_unconfirmed',stop_error=str(exc))
        state['last_estimate']=latest
        # Keep the recorder alive until producers have stopped.
        ordered=sorted(children,key=lambda c: c.args[:3]==['ros2','bag','record'])
        for child in ordered:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=5)
        for log in logs:log.close()
        command_log.close();(out/'trial.json').write_text(json.dumps(state,indent=2))
        node.destroy_node();rclpy.try_shutdown();print('Results: '+str(out),flush=True)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit(130)
