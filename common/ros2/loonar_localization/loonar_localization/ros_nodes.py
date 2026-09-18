"""ROS2 adapters. No vehicle command publisher. TF publishing is opt-in."""
from collections import deque
from dataclasses import fields
import json
import math
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.time import Time
from geometry_msgs.msg import Twist, TransformStamped
from sensor_msgs.msg import Imu, PointCloud2, JointState
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from sensor_msgs_py import point_cloud2
from tf2_ros import Buffer, TransformListener, TransformBroadcaster
from message_filters import Subscriber, ApproximateTimeSynchronizer
from scipy.spatial.transform import Rotation
from .core import Config, Sample, Estimator, PrimitiveManager, Primitive, PrimitiveSequence
from .registration import ICPConfig, StopCorrection, transform


def seconds(stamp):
    return stamp.sec+stamp.nanosec*1e-9


def ros_stamp(t):
    return Time(nanoseconds=int(round(t*1e9))).to_msg()


def matrix(msg):
    q = msg.rotation; p = msg.translation
    T = np.eye(4); T[:3, :3] = Rotation.from_quat([q.x, q.y, q.z, q.w]).as_matrix(); T[:3, 3] = [p.x, p.y, p.z]
    return T


def tf_message(T, parent, child, stamp):
    m = TransformStamped(); m.header.stamp = stamp; m.header.frame_id = parent; m.child_frame_id = child
    m.transform.translation.x, m.transform.translation.y, m.transform.translation.z = map(float, T[:3, 3])
    q = Rotation.from_matrix(T[:3, :3]).as_quat()
    m.transform.rotation.x, m.transform.rotation.y, m.transform.rotation.z, m.transform.rotation.w = map(float, q)
    return m


class DRNode(Node):
    def __init__(self):
        super().__init__('loonar_dead_reckoning')
        self.config = Config(**{f.name: self.declare_parameter(f.name, getattr(Config(), f.name)).value for f in fields(Config)})
        self.core = Estimator(self.config, self.declare_parameter('initial_gyro_bias', [0., 0., 0.]).value)
        self.manager = PrimitiveManager(self.declare_parameter('slow_speed', .075).value)
        self.publish_tf = self.declare_parameter('publish_odom_tf', False).value
        self.prior_enabled = self.declare_parameter('primitive_enabled', True).value
        self.acceleration_valid = self.declare_parameter('gravity_compensation_validated', False).value
        self.odom_frame = self.declare_parameter('odom_frame', 'odom').value
        self.base_frame = self.declare_parameter('base_frame', 'base_link').value
        self.max_age = self.declare_parameter('max_sensor_age', .25).value
        self.command_prior_age = self.declare_parameter('command_prior_age', .5).value
        self.sync_slop = self.declare_parameter('sync_slop', .015).value
        self.command_time = None
        self.side_previous = None
        self.side_rates = None
        self.side_topic = self.declare_parameter('wheel_position_topic', '').value
        self.side_names = self.declare_parameter('wheel_position_names', ['left', 'right']).value
        self.side_scale = self.declare_parameter('wheel_position_scale_to_m', 1.).value
        if self.side_topic:
            self.create_subscription(JointState, self.side_topic, self.side_wheels, rclpy.qos.qos_profile_sensor_data)
        self.buf = Buffer(); self.listener = TransformListener(self.buf, self); self.tf = TransformBroadcaster(self)
        self.odom = self.create_publisher(Odometry, 'localization/dr', 10)
        self.diag = self.create_publisher(String, 'localization/state', 10)
        self.create_subscription(Twist, 'cmd_vel', self.command, 10)
        self.wheel = Subscriber(self, Odometry, 'wheel/odom', qos_profile=rclpy.qos.qos_profile_sensor_data)
        self.imu = Subscriber(self, Imu, 'imu', qos_profile=rclpy.qos.qos_profile_sensor_data)
        self.sync = ApproximateTimeSynchronizer([self.wheel, self.imu], 100, self.sync_slop)
        self.sync.registerCallback(self.update)
        self.last_valid_receipt = None
        self.create_timer(.2, self.check_stale)

    def side_wheels(self, msg):
        t = seconds(msg.header.stamp)
        try:
            p = np.array([msg.position[msg.name.index(name)] for name in self.side_names])*self.side_scale
            if not np.isfinite(p).all():
                raise ValueError('nonfinite wheel positions')
            previous = self.side_previous
            self.side_previous = (t, p)
            if previous is not None and 0 < t-previous[0] <= self.config.max_gap:
                self.side_rates = (t, tuple((p-previous[1])/(t-previous[0])))
            else:
                self.side_rates = None
        except (ValueError, IndexError):
            self.side_previous = self.side_rates = None

    def emit(self, payload):
        self.last_diagnostic = payload
        m = String(); m.data = json.dumps(payload, allow_nan=False); self.diag.publish(m)

    def check_stale(self):
        now = self.get_clock().now().nanoseconds/1e9
        if self.last_valid_receipt is None or now-self.last_valid_receipt > self.max_age:
            self.core.detector.reset()
            self.emit(dict(t=now, valid=False, stationary=False, state='DEGRADED', reasons=['sensor_stream_unavailable']))

    def command(self, m):
        self.manager.observe(m.linear.x, m.angular.z)
        self.command_time = self.get_clock().now().nanoseconds/1e9

    def update(self, wheel, imu):
        now = self.get_clock().now().nanoseconds/1e9
        t, ti = seconds(wheel.header.stamp), seconds(imu.header.stamp)
        try:
            if not 0 <= now-min(t, ti) <= self.max_age:
                raise ValueError('stale_or_future_sensor_stamp')
            if imu.angular_velocity_covariance[0] < 0 or imu.linear_acceleration_covariance[0] < 0:
                raise ValueError('imu_channel_marked_unavailable')
            if wheel.child_frame_id != self.base_frame:
                raise ValueError('wheel_twist_not_in_base_frame')
            R = np.eye(3)
            if imu.header.frame_id != self.base_frame:
                tr = self.buf.lookup_transform(self.base_frame, imu.header.frame_id, Time.from_msg(imu.header.stamp))
                R = matrix(tr.transform)[:3, :3]
            g = imu.angular_velocity; a = imu.linear_acceleration
            prior = self.manager.state if self.prior_enabled and self.command_time is not None and now-self.command_time <= self.command_prior_age else Primitive.UNKNOWN
            side_valid = self.side_rates is not None and abs(t-self.side_rates[0]) <= self.sync_slop*2
            if self.side_topic and not side_valid:
                self.core.detector.reset()
            s = Sample(t, wheel.twist.twist.linear.x, wheel.twist.twist.angular.z,
                       R@np.array([g.x, g.y, g.z]), R@np.array([a.x, a.y, a.z]), self.acceleration_valid,
                       self.side_rates[1] if side_valid else ())
            result = self.core.update(s, prior)
            result.update(valid=True, imu_header_delta=ti-t, frame=self.base_frame,
                          wheel_detail_valid=side_valid, wheel_speeds=list(s.wheel_speeds))
            self.last_valid_receipt = now
            self.emit(result)
            m = Odometry(); m.header.stamp = wheel.header.stamp; m.header.frame_id = self.odom_frame; m.child_frame_id = self.base_frame
            x, y, yaw = result['pose']; m.pose.pose.position.x = x; m.pose.pose.position.y = y
            m.pose.pose.orientation.z = math.sin(yaw/2); m.pose.pose.orientation.w = math.cos(yaw/2)
            m.twist.twist.linear.x = result['vx']; m.twist.twist.angular.z = result['wz']
            cov = np.eye(6)*1e6; inds = [0, 1, 5]; cov[np.ix_(inds, inds)] = self.core.cov; m.pose.covariance = cov.ravel().tolist()
            twist_cov = np.eye(6)*1e6; twist_cov[0, 0] = self.config.base_v_variance/max(result['confidence'], .01); twist_cov[5, 5] = self.config.base_w_variance
            m.twist.covariance = twist_cov.ravel().tolist(); self.odom.publish(m)
            if self.publish_tf:
                from .registration import pose_matrix
                self.tf.sendTransform(tf_message(pose_matrix(result['pose']), self.odom_frame, self.base_frame, m.header.stamp))
        except Exception as e:
            self.core.detector.reset()
            self.emit(dict(t=t, valid=False, stationary=False, state='DEGRADED', reasons=[str(e)]))


class RegistrationNode(Node):
    def __init__(self):
        super().__init__('loonar_stop_registration')
        c = ICPConfig(**{f.name: self.declare_parameter(f.name, getattr(ICPConfig(), f.name)).value for f in fields(ICPConfig)})
        self.core = StopCorrection(c, self.declare_parameter('stuck_body_distance', .02).value)
        self.enabled = self.declare_parameter('registration_enabled', False).value
        self.publish_tf = self.declare_parameter('publish_map_tf', False).value
        self.base_frame = self.declare_parameter('base_frame', 'base_link').value
        self.odom_frame = self.declare_parameter('odom_frame', 'odom').value
        self.map_frame = self.declare_parameter('map_frame', 'map').value
        self.max_age = self.declare_parameter('max_cloud_age', .5).value
        self.history = deque(maxlen=1000)
        self.stop_id = 0; self.stationary = False
        self.buf = Buffer(); self.listener = TransformListener(self.buf, self); self.tf = TransformBroadcaster(self)
        self.diag = self.create_publisher(String, 'localization/registration', 10)
        self.corrected = self.create_publisher(Odometry, '/odom_tof_test', 10)
        self.create_subscription(String, 'localization/state', self.state, 10)
        self.create_subscription(PointCloud2, 'tof/depth/points', self.cloud, rclpy.qos.qos_profile_sensor_data)
        self.create_timer(.1, self.broadcast)

    def state(self, msg):
        r = json.loads(msg.data)
        stationary = r.get('valid', False) and r.get('stationary', False)
        if stationary and not self.stationary:
            self.stop_id += 1
        self.stationary = stationary
        if r.get('valid', False):
            self.history.append((r['t'], stationary, self.stop_id, r['pose'], r['wheel_distance']))
            if self.enabled:
                from .registration import pose_matrix
                T = self.core.map_odom @ pose_matrix(r['pose'])
                m = Odometry(); m.header.stamp = ros_stamp(r['t']); m.header.frame_id = self.map_frame; m.child_frame_id = self.base_frame
                m.pose.pose.position.x = float(T[0,3]); m.pose.pose.position.y = float(T[1,3])
                q = Rotation.from_matrix(T[:3,:3]).as_quat()
                m.pose.pose.orientation.x,m.pose.pose.orientation.y,m.pose.pose.orientation.z,m.pose.pose.orientation.w = map(float,q)
                m.twist.twist.linear.x = float(r['vx']); m.twist.twist.angular.z = float(r['wz'])
                m.pose.covariance = (np.eye(6)*1e6).ravel().tolist()
                self.corrected.publish(m)
        else:
            self.history.clear()

    def broadcast(self):
        if self.enabled and self.publish_tf and self.core.anchor is not None:
            self.tf.sendTransform(tf_message(self.core.map_odom, self.map_frame, self.odom_frame, self.get_clock().now().to_msg()))

    def cloud(self, msg):
        if not self.enabled:
            return
        t = seconds(msg.header.stamp); now = self.get_clock().now().nanoseconds/1e9
        try:
            if not 0 <= now-t <= self.max_age:
                raise ValueError('stale_or_future_cloud')
            # Require a recent stationary sample at or before acquisition, not processing time.
            past = [r for r in self.history if 0 <= t-r[0] <= .04 and r[1]]
            if not past or not self.stationary:
                raise ValueError('no_stationary_evidence_at_cloud_stamp')
            h = past[-1]
            if h[2] == self.core.last_stop_id:
                return
            if msg.width*msg.height > 1_000_000:
                raise ValueError('cloud_exceeds_input_bound')
            pts = point_cloud2.read_points_numpy(msg, field_names=('x', 'y', 'z'), skip_nans=True).reshape(-1, 3)
            if msg.header.frame_id != self.base_frame:
                tr = self.buf.lookup_transform(self.base_frame, msg.header.frame_id, Time.from_msg(msg.header.stamp))
                pts = transform(matrix(tr.transform), pts)
            r = self.core.submit(h[2], t, pts, h[3], h[4])
            r['dr_stamp'] = h[0]
        except Exception as e:
            r = dict(accepted=False, reason=str(e), stamp=t)
        m = String(); m.data = json.dumps(r, allow_nan=False); self.diag.publish(m)


class PrimitiveNode(Node):
    """Publishes intent for the autonomy integration, never /cmd_vel."""
    def __init__(self):
        super().__init__('loonar_primitive_manager')
        self.sequence = PrimitiveSequence(**{k: self.declare_parameter(k, v).value for k, v in
            dict(slow=.05, normal=.1, angular=.15, distance_tolerance=.01, yaw_tolerance=.02).items()})
        self.enabled = self.declare_parameter('sequence_enabled', True).value
        self.publisher = self.create_publisher(String, 'localization/primitive_intent', 10)
        self.create_subscription(String, 'localization/primitive_goal', self.goal, 10)
        self.create_subscription(String, 'localization/state', self.feedback, 10)

    def emit(self, result):
        m = String(); m.data = json.dumps(result, allow_nan=False); self.publisher.publish(m)

    def goal(self, msg):
        try:
            if not self.enabled:
                raise ValueError('sequence_disabled')
            goal = json.loads(msg.data)
            if goal.get('cancel', False):
                self.emit(self.sequence.cancel())
            else:
                self.sequence.start(float(goal['relative_yaw']), float(goal['distance']), bool(goal.get('slow', False)))
        except (ValueError, KeyError, TypeError) as e:
            self.emit(dict(error=str(e)))

    def feedback(self, msg):
        if self.enabled and self.sequence.queue:
            self.emit(self.sequence.update(json.loads(msg.data)))


def run(cls):
    rclpy.init(); node = cls()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node(); rclpy.shutdown()


def dr_main():
    run(DRNode)


def registration_main():
    run(RegistrationNode)


def primitive_main():
    run(PrimitiveNode)
