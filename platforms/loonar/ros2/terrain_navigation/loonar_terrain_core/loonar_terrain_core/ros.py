"""ROS adapters. All measurement age/sequence decisions use ROS time."""

import math
from collections import deque
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    qos_profile_sensor_data,
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
)
from rcl_interfaces.msg import SetParametersResult
from tf2_ros import Buffer, TransformListener
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from .algorithms import fresh

SENSOR = qos_profile_sensor_data
STATUS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
MAP = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
DEFAULTS = dict(
    sensor_timeout=0.3,
    sync_tolerance=0.06,
    base_frame="base_link",
    wheel_velocity_threshold=0.025,
    gyro_threshold=0.04,
    gyro_std_threshold=0.015,
    accel_std_threshold=0.12,
    minimum_duration=0.5,
    settling_min_time=0.4,
    max_step_up=0.035,
    max_step_down=0.035,
    max_slope=0.22,
    max_cross_slope=0.17,
    max_roughness=0.012,
    max_drop_depth=0.035,
    max_unknown_ratio=0.0,
    min_confidence=0.6,
    robot_width=0.30,
    robot_length=0.32,
    wheel_track=0.210,
    wheel_radius=0.098,
    tail_offset=0.20,
    safety_margin=0.04,
    heading_min=-0.6981317,
    heading_max=0.6981317,
    heading_step=0.1745329,
    lookahead_distance=0.8,
    min_drive_distance=0.10,
    max_drive_distance=0.25,
    distance_safety_factor=0.6,
    stopping_margin=0.07,
    w_slope=1.0,
    w_roughness=1.0,
    w_step=1.0,
    w_unknown=2.0,
    w_risk=2.0,
    w_turn=0.3,
    w_heading_change=0.3,
    w_progress=1.0,
    map_max_age=3.0,
    straight_slow_speed=0.05,
    straight_normal_speed=0.10,
    rotate_speed=0.20,
    yaw_tolerance=0.025,
    distance_tolerance=0.005,
    settle_gyro_threshold=0.035,
    straight_yaw_kp=1.2,
    straight_yaw_kd=0.15,
    max_heading_correction=0.20,
    distance_kp=0.8,
    rotate_kp=1.0,
    max_primitive_timeout=20.0,
    max_rotate_angle=1.0,
    max_roll=0.35,
    max_pitch=0.35,
    max_shock=20.0,
    max_wheel_speed=0.5,
    frame_count=4,
    capture_timeout=3.0,
    phase_timeout=25.0,
    recovery_step=0.35,
    recovery_max_angle=6.2831853,
    recovery_rotation_clearance_verified=False,
    calibration_confirmed=False,
    enable_motion=False,
    autostart=False,
    brake_reaction_time=0.10,
    brake_deceleration=0.20,
    collision_half_width=0.20,
    collision_min_height=-0.063,
    collision_max_height=0.602,
    collision_min_points=4,
    min_valid_ratio=0.1,
    amplitude_threshold=30.0,
    min_range=0.15,
    max_range=2.5,
    pixel_stride=4,
    gravity_magnitude_min=8.0,
    gravity_magnitude_max=12.0,
)


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


def rotation(q):
    v = np.array([q.x, q.y, q.z, q.w], dtype=float)
    norm = np.linalg.norm(v)
    if not np.isfinite(v).all() or not 0.9 <= norm <= 1.1:
        raise ValueError("invalid quaternion")
    x, y, z, w = v / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def level_rotation(gravity):
    g = np.array(gravity, dtype=float, copy=True)
    g /= np.linalg.norm(g)
    # R = Ry(pitch) Rx(roll): removes tilt, with no global yaw dependence.
    roll = math.atan2(g[1], g[2])
    pitch = math.atan2(-g[0], math.hypot(g[1], g[2]))
    cr, sr, cp, sp = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch)
    return (
        np.array([[cp, sp * sr, sp * cr], [0, cr, -sr], [-sp, cp * sr, cp * cr]]),
        roll,
        pitch,
    )


def image_array(msg):
    types = {"32FC1": ("f4", 4), "16UC1": ("u2", 2), "mono16": ("u2", 2)}
    if msg.encoding not in types:
        raise ValueError("unsupported image encoding " + msg.encoding)
    kind, size = types[msg.encoding]
    if (
        not msg.width
        or not msg.height
        or msg.step < msg.width * size
        or len(msg.data) < msg.step * msg.height
    ):
        raise ValueError("malformed image")
    return np.ndarray(
        (msg.height, msg.width),
        dtype=np.dtype((">" if msg.is_bigendian else "<") + kind),
        buffer=bytes(msg.data),
        strides=(msg.step, size),
    ).astype(float)


class Runtime(Node):
    def __init__(self, name, keys=(), extra=None):
        super().__init__(name)
        self.defaults = {k: DEFAULTS[k] for k in keys}
        self.defaults.update(extra or {})
        for k, v in self.defaults.items():
            self.declare_parameter(k, v)
        self.add_on_set_parameters_callback(self.validate)
        check = self.validate([])
        if not check.successful:
            raise ValueError(check.reason)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.diag = self.create_publisher(DiagnosticArray, "/diagnostics", STATUS)

    @property
    def p(self):
        return {k: self.get_parameter(k).value for k in self.defaults}

    def validate(self, changes):
        p = self.p
        for v in changes:
            if v.name in p:
                if getattr(self, "busy", False):
                    return SetParametersResult(
                        successful=False,
                        reason="stop current operation before changing parameters",
                    )
                p[v.name] = v.value
        # Heights are coordinates in the levelled base frame. A CAD base at
        # wheel-axle height puts the ground (and low obstacles) below z=0.
        signed = {
            "heading_min",
            "heading_max",
            "collision_min_height",
            "collision_max_height",
            "self_z_min",
            "self_z_max",
        }
        zero_ok = {
            "max_unknown_ratio",
            "tail_offset",
            "safety_margin",
            "amplitude_threshold",
        }
        for k, v in p.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if not math.isfinite(v) or (
                    k not in signed
                    and (
                        v < 0
                        or (v == 0 and k not in zero_ok and not k.startswith("w_"))
                    )
                ):
                    return SetParametersResult(successful=False, reason="invalid " + k)
        for lo, hi in [
            ("min_range", "max_range"),
            ("heading_min", "heading_max"),
            ("min_drive_distance", "max_drive_distance"),
            ("gravity_magnitude_min", "gravity_magnitude_max"),
            ("collision_min_height", "collision_max_height"),
        ]:
            if lo in p and hi in p and p[lo] > p[hi]:
                return SetParametersResult(
                    successful=False, reason=lo + " exceeds " + hi
                )
        for k in (
            "distance_safety_factor",
            "min_confidence",
            "max_unknown_ratio",
            "min_valid_ratio",
        ):
            if k in p and p[k] > 1:
                return SetParametersResult(successful=False, reason=k + " exceeds 1")
        if "frame_count" in p and p["frame_count"] not in (3, 4):
            return SetParametersResult(
                successful=False, reason="frame_count must be 3 or 4"
            )
        if (
            all(k in p for k in ("heading_min", "heading_max", "heading_step"))
            and (p["heading_max"] - p["heading_min"]) / p["heading_step"] > 180
        ):
            return SetParametersResult(
                successful=False, reason="too many candidate headings"
            )
        if (
            "robot_width" in p
            and "wheel_track" in p
            and p["robot_width"] < p["wheel_track"]
        ):
            return SetParametersResult(
                successful=False, reason="footprint narrower than wheel track"
            )
        return SetParametersResult(successful=True)

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def transform(self, frame, stamp):
        t = self.tf.lookup_transform(
            self.p.get("base_frame", "base_link"),
            frame,
            rclpy.time.Time.from_msg(stamp),
        ).transform
        return rotation(t.rotation), np.array(
            [t.translation.x, t.translation.y, t.translation.z]
        )

    def report(self, text, error=False):
        m = DiagnosticArray()
        m.header.stamp = self.get_clock().now().to_msg()
        d = DiagnosticStatus()
        d.name = self.get_name()
        d.hardware_id = "loonar"
        d.level = DiagnosticStatus.ERROR if error else DiagnosticStatus.OK
        d.message = text
        m.status = [d]
        self.diag.publish(m)


class Sensors:
    """Supports the existing separate gyro/accel/gravity ROS topics without firmware changes."""

    def __init__(self, node):
        from sensor_msgs.msg import Imu, JointState
        from geometry_msgs.msg import Vector3Stamped
        from loonar_msgs.msg import BaseState, SafetyState

        self.node = node
        self.gyro = self.accel = self.gravity = self.wheels = self.base = (
            self.safety
        ) = None
        self.stamps = {}
        self.gravity_history = deque(maxlen=64)
        self.subs = []
        for topic, cls, cb, qos in [
            ("/imu/data", Imu, self.on_gyro, SENSOR),
            ("/imu/accel", Imu, self.on_accel, SENSOR),
            ("/imu/gravity", Vector3Stamped, self.on_gravity, SENSOR),
            ("/wheel_states", JointState, self.on_wheels, SENSOR),
            ("/loonar/base/state", BaseState, self.on_base, STATUS),
            ("/loonar/safety/emergency_stop", SafetyState, self.on_safety, STATUS),
        ]:
            self.subs.append(node.create_subscription(cls, topic, cb, qos))

    def save(self, key, msg, values):
        t = seconds(msg.header.stamp)
        if not fresh(t, self.node.now_s(), self.node.p["sensor_timeout"]):
            return
        if key in self.stamps and t <= self.stamps[key]:
            return
        if isinstance(values, np.ndarray) and not np.isfinite(values).all():
            return
        setattr(self, key, values)
        self.stamps[key] = t

    def vector(self, key, msg, v):
        try:
            rot, _ = self.node.transform(msg.header.frame_id, msg.header.stamp)
            self.save(key, msg, rot @ np.array([v.x, v.y, v.z]))
        except Exception:
            self.stamps.pop(key, None)

    def on_gyro(self, m):
        if m.angular_velocity_covariance[0] >= 0:
            self.vector("gyro", m, m.angular_velocity)
        if m.linear_acceleration_covariance[0] >= 0:
            self.vector("accel", m, m.linear_acceleration)

    def on_accel(self, m):
        if m.linear_acceleration_covariance[0] >= 0:
            self.vector("accel", m, m.linear_acceleration)

    def on_gravity(self, m):
        previous = self.stamps.get("gravity")
        self.vector("gravity", m, m.vector)
        stamp = self.stamps.get("gravity")
        if stamp is not None and stamp != previous:
            if self.gravity_history and stamp < self.gravity_history[-1][0]:
                self.gravity_history.clear()
            self.gravity_history.append((stamp, self.gravity.copy()))

    def gravity_at(self, stamp, tolerance):
        samples = [
            (t, g)
            for t, g in self.gravity_history
            if fresh(t, self.node.now_s(), self.node.p["sensor_timeout"])
            and abs(t - stamp) <= tolerance
        ]
        return (
            min(samples, key=lambda sample: abs(sample[0] - stamp))[1]
            if samples
            else None
        )

    def on_wheels(self, m):
        try:
            ids = [m.name.index(k) for k in ("left_wheel", "right_wheel")]
            a = np.array([[m.position[i], m.velocity[i]] for i in ids])
            self.save("wheels", m, a)
        except (ValueError, IndexError):
            self.stamps.pop("wheels", None)

    def on_base(self, m):
        self.save("base", m, m)

    def on_safety(self, m):
        self.save("safety", m, m)

    def valid(self, *keys):
        now = self.node.now_s()
        timeout = self.node.p["sensor_timeout"]
        # A ROS time reset invalidates all cached measurements, allowing new epoch samples.
        if any(t > now for t in self.stamps.values()):
            self.stamps.clear()
        return all(fresh(self.stamps.get(k), now, timeout) for k in keys)


def spin(node_class):
    # Keep the context alive until zero velocity has been published. Default
    # rclpy signal handling shuts it down before our finally block can do that.
    import signal
    from rclpy.signals import SignalHandlerOptions

    stopping = [False]

    def request_stop(_signal, _frame):
        stopping[0] = True

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    previous = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    node = None
    try:
        node = node_class()
        while rclpy.ok() and not stopping[0]:
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        if node:
            if hasattr(node, "stop_output"):
                node.stop_output()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
