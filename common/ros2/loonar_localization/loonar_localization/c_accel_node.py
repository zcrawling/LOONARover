"""Read-only sensor adapter; publishes only experimental odometry/diagnostics."""
import copy
import csv
from dataclasses import fields
import json
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from geometry_msgs.msg import Quaternion
from message_filters import Subscriber, ApproximateTimeSynchronizer, SimpleFilter
from tf2_ros import Buffer, TransformListener
from scipy.spatial.transform import Rotation
from .c_accel import CConfig, CEstimator
from .ros_nodes import seconds, matrix, ros_stamp


class CTestNode(Node):
    def __init__(self):
        super().__init__('odom_c_test_estimator')
        self.core=CEstimator(CConfig(**{f.name:self.declare_parameter(f.name,getattr(CConfig(),f.name)).value for f in fields(CConfig)}))
        self.mode=self.declare_parameter('acceleration_mode','unvalidated').value
        if self.mode not in ('unvalidated','linear','orientation','static_bias_experiment'):raise ValueError('invalid acceleration_mode')
        self.orientation_validated=self.declare_parameter('orientation_validated',False).value
        self.offset=self.declare_parameter('imu_time_offset_s',0.).value
        self.max_age=self.declare_parameter('max_age',.2).value
        self.max_wz=self.declare_parameter('max_experiment_wz',.05).value
        self.base=self.declare_parameter('base_frame','base_link').value
        output=Path(self.declare_parameter('output_dir','/tmp/loonar_c_test').value);output.mkdir(parents=True,exist_ok=True)
        self.log=(output/'samples.csv').open('x',newline=''); self.writer=None
        self.windows=(output/'windows.jsonl').open('x');self.last_window=None
        (output/'config.json').write_text(json.dumps(dict(acceleration_mode=self.mode,orientation_validated=self.orientation_validated,
             imu_time_offset_s=self.offset,**vars(self.core.c)),indent=2))
        self.buf=Buffer();self.listener=TransformListener(self.buf,self)
        self.state=None;self.phases=[]
        self.create_subscription(String,'localization/state',self.on_state,10)
        self.create_subscription(String,'c_test/phase',self.on_phase,10)
        self.odom=self.create_publisher(Odometry,'/odom_c_test',10)
        self.diag=self.create_publisher(String,'c_test/diagnostics',10)
        imu=Subscriber(self,Imu,'/imu',qos_profile=rclpy.qos.qos_profile_sensor_data)
        self.shifted=SimpleFilter();imu.registerCallback(self.shift)
        wheel=Subscriber(self,Odometry,'/wheel/odom',qos_profile=rclpy.qos.qos_profile_sensor_data)
        v1=Subscriber(self,Odometry,'/localization/dr',qos_profile=rclpy.qos.qos_profile_sensor_data)
        self.sync=ApproximateTimeSynchronizer([self.shifted,wheel,v1],50,.025);self.sync.registerCallback(self.update)
        self.get_logger().info('C experiment only; gravity mode='+self.mode+'; no TF or baseline writes')
        if self.mode=='static_bias_experiment':self.get_logger().warning('Constant attitude assumption: pitch changes contaminate C. Not gravity compensated.')

    def on_state(self,msg):self.state=json.loads(msg.data)
    def on_phase(self,msg):
        r=json.loads(msg.data)
        if r['phase'] not in ('STOP','ACCEL','CRUISE','DECEL'):return
        self.phases.append((float(r['t']),r['phase']));self.phases=self.phases[-500:]
    def shift(self,msg):
        msg=copy.deepcopy(msg);msg.header.stamp=ros_stamp(seconds(msg.header.stamp)+self.offset);self.shifted.signalMessage(msg)

    def update(self,imu,wheel,v1):
        t=seconds(wheel.header.stamp);ti=seconds(imu.header.stamp);now=self.get_clock().now().nanoseconds/1e9
        phase=next((p for ts,p in reversed(self.phases) if ts<=t),'STOP')
        st=self.state or {};stationary=bool(st.get('valid') and st.get('stationary') and abs(t-st.get('t',0))<.08)
        try:
            valid=0<=now-min(t,ti,seconds(v1.header.stamp))<=self.max_age
            valid &= wheel.child_frame_id==self.base and v1.child_frame_id==self.base
            valid &= imu.linear_acceleration_covariance[0]>=0 and abs(v1.twist.twist.angular.z)<=self.max_wz
            acc=np.array([imu.linear_acceleration.x,imu.linear_acceleration.y,imu.linear_acceleration.z])
            R=np.eye(3)
            if imu.header.frame_id!=self.base:
                R=matrix(self.buf.lookup_transform(self.base,imu.header.frame_id,Time.from_msg(imu.header.stamp)).transform)[:3,:3]
            if self.mode=='orientation':
                q=imu.orientation;quat=np.array([q.x,q.y,q.z,q.w])
                if not self.orientation_validated or imu.orientation_covariance[0]<0 or abs(np.linalg.norm(quat)-1)>.01:
                    valid=False
                else:acc-=Rotation.from_quat(quat).inv().apply([0,0,9.80665])
            elif self.mode=='unvalidated':valid=False
            # linear acceleration is already gravity-free: do not subtract gravity again.
            acc=R@acc
            q=v1.pose.pose.orientation;yaw=Rotation.from_quat([q.x,q.y,q.z,q.w]).as_euler('xyz')[2]
            r=self.core.update(t,wheel.twist.twist.linear.x,float(acc[0]),yaw,v1.twist.twist.angular.z,
                               phase,stationary,valid,[v1.pose.pose.position.x,v1.pose.pose.position.y])
            r.update(acceleration_mode=self.mode,imu_header_delta_s=ti-t,bias_ready=self.core.bias is not None)
            m=copy.deepcopy(v1);m.header.stamp=wheel.header.stamp
            m.pose.pose.position.x,m.pose.pose.position.y=r['pose'][:2]
            m.twist.twist.linear.x=r['vx_corrected']
            # No calibrated covariance for the C experiment; do not copy V1 certainty.
            m.pose.covariance=(np.eye(6)*1e6).ravel().tolist();m.twist.covariance=(np.eye(6)*1e6).ravel().tolist()
            self.odom.publish(m)
            flat={k:v for k,v in r.items() if k!='pose'};flat.update(x=r['pose'][0],y=r['pose'][1],yaw=r['pose'][2])
            if self.writer is None:self.writer=csv.DictWriter(self.log,fieldnames=list(flat));self.writer.writeheader()
            self.writer.writerow(flat);self.log.flush()
            if self.core.last_window is not None and self.core.last_window is not self.last_window:
                self.windows.write(json.dumps(self.core.last_window,allow_nan=False)+'\n');self.windows.flush();self.last_window=self.core.last_window
        except Exception as exc:
            self.core.c_valid=False;self.core.run_bad=True
            r=dict(t=t,C_valid=False,error=str(exc))
        msg=String();msg.data=json.dumps(r,allow_nan=False);self.diag.publish(msg)

    def destroy_node(self):
        self.log.close();self.windows.close();return super().destroy_node()


def main():
    rclpy.init();node=CTestNode()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()


if __name__ == "__main__":main()
