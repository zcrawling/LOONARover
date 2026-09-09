"""ROS integration fixture. Run in an isolated container/domain, never on a rover graph."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from sensor_msgs.msg import Imu
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import TwistWithCovarianceStamped
    from loonar_imu_vibration.node import CorrectionNode
    ROS = True
except ImportError:
    ROS = False

from loonar_imu_vibration.core import Config, SCHEMA, features


@unittest.skipUnless(ROS and os.environ.get('LOONAR_ISOLATED_ROS_TEST') == '1', 'Requires isolated ROS test environment')
class RuntimeTest(unittest.TestCase):
    def test_correction_then_missing_imu_fallback_without_pose_or_command(self):
        cfg=Config()
        imu=[[i*.01,0,0,9.81,0,0,0] for i in range(101)]
        wheel=[[i*.02,.1,0] for i in range(51)]
        f,_=features(imu,wheel,1,cfg)
        names=sorted(f)
        model=dict(schema=SCHEMA,config=asdict(cfg),profile_id='synthetic-test-only',
                   feature_names=names,mean=[f[n] for n in names],scale=[1.]*len(names),
                   coef=[0.]*len(names),intercept=.5)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.json'
            path.write_text(json.dumps(model))
            rclpy.init(args=['--ros-args','-p','enabled:=true','-p','profile_id:=synthetic-test-only',
                            '-p','model_path:='+str(path)])
            node=CorrectionNode()
            source=Node('synthetic_vibration_source')
            ip=source.create_publisher(Imu,'/imu/data',10)
            wp=source.create_publisher(Odometry,'/wheel/odom',10)
            outputs=[]
            sub=source.create_subscription(TwistWithCovarianceStamped,'/wheel/twist_corrected',outputs.append,100)
            executor=SingleThreadedExecutor()
            executor.add_node(node)
            executor.add_node(source)
            try:
                begin=time.monotonic()
                i=0
                while time.monotonic()-begin<3:
                    elapsed=time.monotonic()-begin
                    t=source.get_clock().now().to_msg()
                    if elapsed<2.5:
                        m=Imu()
                        m.header.stamp=t
                        m.header.frame_id='imu_link'
                        m.linear_acceleration.z=9.81
                        ip.publish(m)
                    if i%2==0:
                        w=Odometry()
                        w.header.stamp=t
                        w.header.frame_id='odom'
                        w.child_frame_id='base_link'
                        w.twist.twist.linear.x=.1
                        w.twist.covariance[0]=.01
                        wp.publish(w)
                    for _ in range(8):executor.spin_once(timeout_sec=0)
                    time.sleep(.01)
                    i+=1
                for _ in range(30):executor.spin_once(timeout_sec=.005)
                self.assertGreater(len(outputs),20)
                self.assertTrue(any(abs(m.twist.twist.linear.x-.05)<1e-6 for m in outputs))
                self.assertAlmostEqual(outputs[-1].twist.twist.linear.x,.1)
                self.assertTrue(all(m.twist.covariance[0]>=.01 for m in outputs))
                self.assertTrue(all(m.header.frame_id=='base_link' for m in outputs))
                topics=dict(source.get_topic_names_and_types())
                self.assertNotIn('/cmd_vel',topics)
                self.assertNotIn('/tf',topics)
                self.assertNotIn('/wheel/odom_corrected',topics)
            finally:
                executor.shutdown()
                source.destroy_node()
                node.destroy_node()
                rclpy.shutdown()


if __name__=='__main__':unittest.main()
