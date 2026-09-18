"""Explicitly executed ramp experiment; independent of V1 and its state machine."""
import argparse
import json
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String


def profile(t,speed,ramp,cruise,decel):
    if t<ramp:return 'ACCEL',speed*t/ramp
    if t<ramp+cruise:return 'CRUISE',speed
    if t<ramp+cruise+decel:return 'DECEL',speed*(1-(t-ramp-cruise)/decel)
    return 'STOP',0.


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--speed',type=float,default=.25);p.add_argument('--ramp',type=float,default=2.5)
    p.add_argument('--cruise',type=float,default=2.);p.add_argument('--decel',type=float,default=2.5)
    p.add_argument('--stop',type=float,default=4.);p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if min(args.speed,args.ramp,args.cruise,args.decel,args.stop)<=0:p.error('durations/speed must be positive')
    print('Nominal commanded distance:',args.speed*(args.ramp/2+args.cruise+args.decel/2),'m (not actual-distance control)',flush=True)
    if not args.execute:
        print('Dry run. Add --execute to publish motion commands.');return
    rclpy.init();node=Node('c_ramp_experiment');cmd=node.create_publisher(Twist,'/cmd_vel',10);phase=node.create_publisher(String,'/c_test/phase',10)
    latest={}
    def receive(msg):latest.update(json.loads(msg.data))
    node.create_subscription(String,'/c_test/diagnostics',receive,10)
    def send(name,speed):
        m=String();m.data=json.dumps(dict(t=node.get_clock().now().nanoseconds/1e9,phase=name));phase.publish(m)
        m=Twist();m.linear.x=speed;cmd.publish(m)
    try:
        start=time.monotonic()
        while time.monotonic()-start<args.stop:
            send('STOP',0.);rclpy.spin_once(node,timeout_sec=.01);time.sleep(.01)
        now=node.get_clock().now().nanoseconds/1e9
        if not latest.get('bias_ready') or not latest.get('acceleration_valid') or now-latest.get('t',0)>.2:
            raise RuntimeError('No fresh stationary bias/valid acceleration. Select verified input mode and run C estimator first.')
        start=time.monotonic();duration=args.ramp+args.cruise+args.decel+args.stop
        while time.monotonic()-start<duration:
            name,v=profile(time.monotonic()-start,args.speed,args.ramp,args.cruise,args.decel)
            send(name,v);rclpy.spin_once(node,timeout_sec=.01);time.sleep(.01)
    except KeyboardInterrupt:pass
    finally:
        for _ in range(5):send('STOP',0.);rclpy.spin_once(node,timeout_sec=.01)
        node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
