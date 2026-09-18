"""Run in an isolated ROS container. No vehicle topics are published as commands."""
import rclpy
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from loonar_localization.ros_nodes import DRNode,RegistrationNode,PrimitiveNode,ros_stamp
from loonar_localization.core import Primitive

rclpy.init()
dr=DRNode();registration=RegistrationNode();primitive=PrimitiveNode()
try:
    assert not dr.publish_tf and not registration.enabled and not registration.publish_tf
    now=dr.get_clock().now().nanoseconds/1e9
    dr.manager.state=Primitive.STRAIGHT_NORMAL;dr.command_time=now
    for i in range(6):
        t=now-.10+i*.01
        wheel=Odometry();wheel.header.stamp=ros_stamp(t);wheel.child_frame_id='base_link';wheel.twist.twist.linear.x=.1
        imu=Imu();imu.header.stamp=wheel.header.stamp;imu.header.frame_id='base_link';imu.linear_acceleration.z=9.81
        dr.update(wheel,imu)
    assert dr.core.last is not None
    assert dr.core.pose[0]>.004
    assert dr.core.last['longitudinal_score'] is None
    print('ROS nodes initialize; paired messages produce DR; TF and registration default off.')
finally:
    dr.destroy_node();registration.destroy_node();primitive.destroy_node();rclpy.shutdown()
