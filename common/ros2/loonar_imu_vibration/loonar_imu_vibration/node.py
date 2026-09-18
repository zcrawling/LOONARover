"""Shadow-mode longitudinal correction; never publishes pose, TF or cmd_vel."""
from dataclasses import asdict
import copy
import json
import math
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TwistWithCovarianceStamped
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_msgs.msg import Float64

from .core import Config, Engine, Predictor


def stamp(m):
    return m.header.stamp.sec+m.header.stamp.nanosec/1e9


class CorrectionNode(Node):
    def __init__(self):
        super().__init__('imu_vibration_correction_node')
        cfg = Config(**{k: self.declare_parameter(k,v).value for k,v in asdict(Config()).items()})
        self.enabled = self.declare_parameter('enabled', False).value
        self.profile = self.declare_parameter('profile_id', 'unset').value
        self.max_age = self.declare_parameter('max_stamp_age_s', 0.2).value
        self.imu_frame = self.declare_parameter('imu_frame', 'imu_link').value
        self.wheel_frame = self.declare_parameter('wheel_frame', 'base_link').value
        path = self.declare_parameter('model_path', '').value
        model = None
        try:
            if path:
                model = json.loads(Path(path).read_text())
            predictor = Predictor(model, cfg, self.profile,
                                  self.declare_parameter('min_c', 0.0).value,
                                  self.declare_parameter('max_c', 2.0).value,
                                  self.declare_parameter('max_z', 6.0).value,
                                  self.declare_parameter('min_support', 0.05).value)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.get_logger().error(f'Model rejected, using encoder baseline: {error}')
            predictor = Predictor(None, cfg, self.profile)
        if not math.isfinite(self.max_age) or self.max_age <= 0:
            raise ValueError('max_stamp_age_s must be positive')
        self.engine = Engine(cfg, predictor)
        self.previous = None
        self.last_output = None
        self.last_imu_ok = False
        self.output = self.create_publisher(TwistWithCovarianceStamped, '/wheel/twist_corrected', 10)
        self.c_pub = self.create_publisher(Float64, '/terrain_correction/c_v', 10)
        self.conf_pub = self.create_publisher(Float64, '/terrain_correction/confidence', 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/terrain_correction/diagnostics', 10)
        self.create_subscription(Imu, self.declare_parameter('imu_topic', '/imu/data').value,
                                 self.imu, qos_profile_sensor_data)
        self.create_subscription(Odometry, self.declare_parameter('wheel_topic', '/wheel/odom').value,
                                 self.wheel, qos_profile_sensor_data)
        self.create_timer(0.5, self.check_stale)

    def fresh(self, t):
        delta = self.get_clock().now().nanoseconds/1e9-t
        return -self.engine.cfg.max_gap_s <= delta <= self.max_age

    def imu(self, m):
        t = stamp(m)
        if (m.header.frame_id != self.imu_frame or not self.fresh(t)
                or m.linear_acceleration_covariance[0] == -1 or m.angular_velocity_covariance[0] == -1):
            self.engine.imu.clear()
            self.last_imu_ok = False
            return
        a,g = m.linear_acceleration,m.angular_velocity
        self.last_imu_ok = self.engine.add('imu', [t,a.x,a.y,a.z,g.x,g.y,g.z])

    def diagnostics(self, t, c, score, reason, values=None):
        status = DiagnosticStatus(name='longitudinal_correction', hardware_id=self.profile,
            level=DiagnosticStatus.OK if reason == 'ok' else DiagnosticStatus.WARN,
            message=reason,
            values=[KeyValue(key=k,value=str(v)) for k,v in dict(c_v=c, confidence=score,
                confidence_definition='training-feature-support, not probability', **(values or {})).items()])
        message = DiagnosticArray()
        message.header.stamp = t
        message.status = [status]
        self.diag_pub.publish(message)
        self.c_pub.publish(Float64(data=float(c)))
        self.conf_pub.publish(Float64(data=float(score)))

    def wheel(self, m):
        t = stamp(m)
        vx, wz = m.twist.twist.linear.x, m.twist.twist.angular.z
        if not math.isfinite(vx) or not math.isfinite(wz) or m.child_frame_id != self.wheel_frame:
            self.engine.wheel.clear()
            self.previous = None
            self.diagnostics(m.header.stamp, 1.0, 0.0, 'invalid_wheel_input')
            return
        if not self.engine.add('wheel', [t,vx,wz]):
            self.previous = None
        c,score,reason,features = self.engine.estimate(t)
        if not self.fresh(t):
            c,score,reason = 1.0,0.0,'stale_wheel_stamp'
        elif not self.last_imu_ok:
            c,score,reason = 1.0,0.0,'invalid_imu_input'
        elif not self.enabled:
            c,score,reason = 1.0,0.0,'shadow_disabled'
        output = TwistWithCovarianceStamped()
        output.header.stamp = m.header.stamp
        output.header.frame_id = m.child_frame_id
        output.twist = copy.deepcopy(m.twist)
        output.twist.twist.linear.x = vx*c
        covariance = list(m.twist.covariance)
        for j in range(6):
            covariance[j] *= c
            covariance[j*6] *= c
        covariance[0] = max(covariance[0], m.twist.covariance[0])
        output.twist.covariance = covariance
        self.output.publish(output)
        details = {'raw_vx': vx, 'corrected_vx': vx*c, 'covariance_note': 'scaled input with original vx variance floor; model error not calibrated'}
        if self.previous is not None and 0 < t-self.previous <= self.engine.cfg.max_gap_s:
            ds = vx*(t-self.previous)
            details.update(raw_increment_m=ds, corrected_increment_m=c*ds)
        self.previous = t
        self.last_output = self.get_clock().now().nanoseconds/1e9
        if features:
            details.update(features)
        self.diagnostics(m.header.stamp, c, score, reason, details)

    def check_stale(self):
        now = self.get_clock().now()
        if self.last_output is None or now.nanoseconds/1e9-self.last_output > self.max_age:
            self.diagnostics(now.to_msg(), 1.0, 0.0, 'wheel_stream_missing')


def main(args=None):
    rclpy.init(args=args)
    node = CorrectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
