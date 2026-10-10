"""Pi AUTO lifecycle. cFS owns modes; this process never selects AUTO."""
import json
import signal
import subprocess
import sys
import time
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from std_msgs.msg import String
from loonar_msgs.msg import BaseState
from .heading import yaw_from_quaternion


class Supervisor(Node):
    def __init__(self):
        super().__init__('loonar_fly_supervisor')
        self.auto = False
        self.mode_at = None
        self.yaw = None
        self.yaw_at = None
        self.target = None
        self.child = None
        self.stop_at = None
        self.failed = False
        self.publisher = self.create_publisher(String,'/loonar/fly/lifecycle',1)
        self.create_subscription(BaseState,'/loonar/base/state',self.on_base,1)
        self.create_subscription(Imu,'/imu/orientation_raw',self.on_heading,qos_profile_sensor_data)
        self.create_timer(.05,self.tick)

    def on_heading(self,msg):
        try:
            age=self.get_clock().now().nanoseconds*1e-9-msg.header.stamp.sec-msg.header.stamp.nanosec*1e-9
            if not 0<=age<=1:return
            self.yaw=yaw_from_quaternion(msg.orientation);self.yaw_at=time.monotonic()-age
            if self.auto and self.target is None:
                self.target = self.yaw
        except ValueError:pass

    def on_base(self,msg):
        age=self.get_clock().now().nanoseconds*1e-9-msg.header.stamp.sec-msg.header.stamp.nanosec*1e-9
        if not 0<=age<=1:return
        self.mode_at=time.monotonic()-age
        auto=bool(msg.auto_selected)
        if auto and not self.auto:
            self.failed=False
            self.target=self.yaw if self.yaw_at is not None and time.monotonic()-self.yaw_at<1 else None
        self.auto=auto

    def stop_child(self):
        if self.child is not None and self.child.poll() is None and self.stop_at is None:
            self.child.send_signal(signal.SIGINT);self.stop_at=time.monotonic()

    def tick(self):
        now=time.monotonic()
        wanted=self.auto and self.mode_at is not None and now-self.mode_at<=1
        if not wanted:self.stop_child()
        if self.child is not None:
            if self.child.poll() is not None:
                self.failed = wanted and self.stop_at is None
                self.child=None;self.stop_at=None
            elif self.stop_at is not None and now-self.stop_at>2:
                self.child.kill()
        if wanted and self.target is not None and not self.failed and self.child is None:
            command=[sys.executable,'-m','loonar_fly.drive_node','--external-mode','--max-speed','0.2']
            if self.target is not None:command+=['--heading-target',str(self.target)]
            self.child=subprocess.Popen(command)
            self.get_logger().info(f'GCS AUTO: fly started; heading={self.target}')
        self.publisher.publish(String(data=json.dumps(dict(auto_requested=self.auto,
            running=self.child is not None, stopping=self.stop_at is not None,
            failed=self.failed, waiting_heading=wanted and self.target is None, initial_heading_rad=self.target))))

    def close(self):
        self.stop_child()
        if self.child is not None:
            try:self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:self.child.kill();self.child.wait()


def main():
    rclpy.init();node=Supervisor()
    try:rclpy.spin(node)
    except (KeyboardInterrupt,ExternalShutdownException):pass
    finally:
        node.close();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()
