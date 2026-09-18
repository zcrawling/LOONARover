"""Run only inside a network-isolated ROS container, never on the rover graph."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Imu,JointState
    from nav_msgs.msg import Odometry
    ROS=True
except ImportError:
    ROS=False


@unittest.skipUnless(ROS and os.environ.get('LOONAR_ISOLATED_ROS_TEST')=='1','Requires isolated ROS container')
class MotionIntegration(unittest.TestCase):
    def test_sensor_ready_pause_resume_stop(self):
        rclpy.init()
        nodes=[Node(n) for n in ['limo_base_node','loonar_limo_wheel_odometer','ekf_filter_node']]
        executor=SingleThreadedExecutor()
        for n in nodes:executor.add_node(n)
        messages=[]
        sub=nodes[0].create_subscription(Twist,'/cmd_vel',lambda m:messages.append(m.linear.x),10)
        publishers=[(nodes[0].create_publisher(cls,topic,10),cls) for topic,cls in
                    [('/imu',Imu),('/wheel/odometer',JointState),('/wheel/odom',Odometry),('/odometry/filtered',Odometry)]]
        script=Path(__file__).resolve().parents[3]/'platforms/limo/tools/run_odom_motion_test.py'
        process=None
        def until(predicate,timeout=20):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                for pub,cls in publishers:
                    m=cls();m.header.stamp=nodes[0].get_clock().now().to_msg();pub.publish(m)
                executor.spin_once(timeout_sec=.02)
                if predicate():return
            self.fail('Timed out waiting for motion state')
        try:
            with tempfile.TemporaryFile(mode='w+') as log:
                process=subprocess.Popen([sys.executable,str(script),'--linear','.05','--angular','0','--duration','1','--external-stop','--name','isolated_pause_test'],stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
                until(lambda:len(messages)>=5)
                self.assertTrue(all(x==0 for x in messages))
                process.stdin.write('RESUME\n');process.stdin.flush()
                until(lambda:.05 in messages)
                messages.clear()
                process.stdin.write('PAUSE\n');process.stdin.flush()
                until(lambda:len(messages)>=5 and all(x==0 for x in messages[-5:]))
                messages.clear()
                process.stdin.write('RESUME\n');process.stdin.flush()
                until(lambda:.05 in messages)
                process.stdin.write('STOP\n');process.stdin.flush();process.stdin.close()
                until(lambda:process.poll() is not None)
                log.seek(0);output=log.read()
                self.assertEqual(process.returncode,0,output)
                self.assertEqual(messages[-1],0)
                self.assertIn('READY:',output)
                self.assertIn('Saved:',output)
        finally:
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            executor.shutdown()
            for n in nodes:n.destroy_node()
            rclpy.shutdown()


if __name__=='__main__':unittest.main()
