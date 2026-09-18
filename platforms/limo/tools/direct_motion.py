#!/usr/bin/env python3
"""Explicit timed /cmd_vel test. No camera, EKF dependency, or recording."""
import argparse
import math
import signal
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speed',type=float,required=True,help='linear.x in m/s')
    parser.add_argument('--angular',type=float,default=0.,help='angular.z in rad/s')
    parser.add_argument('--duration',type=float,required=True,help='command duration in seconds')
    a=parser.parse_args()
    if not all(math.isfinite(v) for v in [a.speed,a.angular,a.duration]) or a.duration<=0:
        parser.error('Values must be finite and duration must be positive')
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from geometry_msgs.msg import Twist
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node=rclpy.create_node('loonar_direct_motion_test')
    pub=node.create_publisher(Twist,'/cmd_vel',10)
    sent=False
    try:
        deadline=time.monotonic()+5
        while not pub.get_subscription_count() and not stopped and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
        if stopped:return
        if not pub.get_subscription_count():raise RuntimeError('No /cmd_vel subscriber. Start/check limo_base first.')
        print(f'Publishing linear={a.speed} m/s angular={a.angular} rad/s for {a.duration}s',flush=True)
        msg=Twist();msg.linear.x=a.speed;msg.angular.z=a.angular
        deadline=time.monotonic()+a.duration
        while not stopped and time.monotonic()<deadline:
            pub.publish(msg);sent=True
            rclpy.spin_once(node,timeout_sec=0)
            time.sleep(min(.05,max(0,deadline-time.monotonic())))
    finally:
        if sent:
            for _ in range(3):pub.publish(Twist());time.sleep(.05)
            print('Zero velocity sent.',flush=True)
        node.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
