"""Pi AUTO lifecycle. cFS owns modes; this process never selects AUTO."""
import json
import argparse
import time
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from std_msgs.msg import String
from loonar_msgs.msg import BaseState
from .heading import yaw_from_quaternion
from .auto_processes import AutoProcesses, sensor_commands


class Supervisor(Node):
    def __init__(self, params_file=None):
        super().__init__('loonar_fly_supervisor')
        self.auto = False
        self.mode_at = None
        self.yaw = None
        self.yaw_at = None
        self.target = None
        self.processes = AutoProcesses(
            sensor_commands(params_file) if params_file else {},
            self.get_logger().info)
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
            self.processes.rearm()
            self.target=self.yaw if self.yaw_at is not None and time.monotonic()-self.yaw_at<1 else None
        self.auto=auto
        if not auto:
            self.processes.stop()

    def tick(self):
        now=time.monotonic()
        wanted=self.auto and self.mode_at is not None and now-self.mode_at<=1
        self.processes.tick(wanted, self.target)
        self.publisher.publish(String(data=json.dumps(dict(auto_requested=self.auto,
            running='driver' in self.processes.children,
            sensors_running='sensors' in self.processes.children,
            terrain_running='terrain' in self.processes.children,
            stopping=self.processes.stop_at is not None,
            failed=self.processes.failed, failure=self.processes.failure,
            waiting_heading=wanted and self.target is None, initial_heading_rad=self.target))))

    def close(self):
        self.processes.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--params-file', help='Own AUTO sensor stack; omit for externally supplied test sensors')
    args = parser.parse_args()
    rclpy.init(args=[]);node=Supervisor(args.params_file)
    try:rclpy.spin(node)
    except (KeyboardInterrupt,ExternalShutdownException):pass
    finally:
        node.close();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()
