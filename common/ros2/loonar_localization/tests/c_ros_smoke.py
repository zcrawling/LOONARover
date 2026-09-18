"""Isolated container only: synthesized inputs, no cmd_vel publisher."""
import tempfile
import numpy as np
import rclpy
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from loonar_localization.c_accel_node import CTestNode
from loonar_localization.ros_nodes import ros_stamp
rclpy.init(args=['--ros-args','-p','acceleration_mode:=linear','-p','output_dir:='+tempfile.mkdtemp()])
n=CTestNode();n.max_age=20.
try:
    start=n.get_clock().now().nanoseconds/1e9-11
    for s in np.arange(0,10.01,.01):
        if s<2:phase='STOP';v=0.;a=0.;stationary=True
        elif s<4:phase='ACCEL';v=(s-2)*.125;a=.125*.7;stationary=s<2.04
        elif s<5:phase='CRUISE';v=.25;a=0.;stationary=False
        elif s<7:phase='DECEL';v=.25-(s-5)*.125;a=-.125*.7;stationary=False
        else:phase='STOP';v=0.;a=0.;stationary=s>8
        t=start+s;n.phases.append((t,phase));n.state=dict(t=t,valid=True,stationary=stationary)
        imu=Imu();imu.header.stamp=ros_stamp(t);imu.header.frame_id='base_link';imu.linear_acceleration.x=a+.03
        w=Odometry();w.header.stamp=imu.header.stamp;w.child_frame_id='base_link';w.header.frame_id='odom';w.twist.twist.linear.x=v;w.pose.pose.orientation.w=1.
        n.update(imu,w,w)
    assert n.core.c_valid,(n.core.reason,n.core.c_acc,n.core.c_dec)
    assert abs(n.core.c_acc-.7)<.01 and abs(n.core.c_dec-.7)<.01
    print('C ROS smoke: accel/dec estimates',n.core.c_acc,n.core.c_dec,'CSV and windows written; baseline input unchanged.')
finally:n.destroy_node();rclpy.shutdown()
