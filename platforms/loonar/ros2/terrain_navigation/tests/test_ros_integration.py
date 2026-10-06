"""Real Jazzy DDS/actions; isolated domain, synthetic sensors, no hardware IO."""

import math
import os
from pathlib import Path
import signal
import subprocess
import time
import numpy as np
import pytest
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient, ActionServer
from rclpy.qos import qos_profile_sensor_data
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
from geometry_msgs.msg import TransformStamped, Vector3Stamped, Twist
from sensor_msgs.msg import Image, CameraInfo, Imu, JointState
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from std_srvs.srv import Trigger
from loonar_msgs.msg import (
    Stationary,
    SafetyState,
    BaseState,
    TerrainMap,
    TerrainDecision,
    TerrainCell,
)
from loonar_msgs.action import (
    BuildTerrainMap as Build,
    ExecuteMotionPrimitive as Motion,
)
from loonar_msgs.srv import PlanTerrain

ROOT = Path(__file__).resolve().parents[1]


class Harness(Node):
    def __init__(self):
        super().__init__("terrain_test_driver")
        self.children = []
        self.logs = []
        self.callbacks = []
        self.timer = self.create_timer(0.02, self.tick)
        self.command = Twist()
        self.positions = [0.0, 0.0]
        self.last = time.monotonic()
        self.emergency = False
        self.feed = True
        self.tf = StaticTransformBroadcaster(self)
        transforms = []
        for frame in ("imu_link", "tof_optical_frame"):
            t = TransformStamped()
            t.header.stamp = self.get_clock().now().to_msg()
            t.header.frame_id = "base_link"
            t.child_frame_id = frame
            t.transform.rotation.w = 1.0
            if frame == "tof_optical_frame":
                t.transform.translation.z = 0.8
                t.transform.rotation.w = 0.0
                t.transform.rotation.y = 1.0
            transforms.append(t)
        self.tf.sendTransform(transforms)
        self.pubs = {}
        for topic, cls, sensor in [
            ("/imu/data", Imu, True),
            ("/imu/accel", Imu, True),
            ("/imu/gravity", Vector3Stamped, True),
            ("/wheel_states", JointState, True),
            ("/odom/raw", Odometry, True),
            ("/loonar/base/state", BaseState, False),
            ("/loonar/safety/emergency_stop", SafetyState, False),
            ("/loonar/stationary", Stationary, False),
        ]:
            self.pubs[topic] = self.create_publisher(
                cls, topic, qos_profile_sensor_data if sensor else 10
            )
        self.commands = []
        self.create_subscription(Twist, "/cmd_vel", self.on_command, 10)

    def on_command(self, m):
        self.command = m
        self.commands.append((m.linear.x, m.angular.z))

    def launch(self, pkg, exe, **params):
        log = open(ROOT / "log" / f"test-{exe}-{len(self.children)}.log", "w")
        self.logs.append(log)
        cmd = [str(ROOT / "install" / pkg / "lib" / pkg / exe), "--ros-args"]
        for k, v in params.items():
            cmd += ["-p", f"{k}:={str(v).lower() if isinstance(v,bool) else v}"]
        self.children.append(
            subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        )

    def tick(self):
        for callback in self.callbacks:
            callback()

    def pump(self, predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for process in self.children:
                assert (
                    process.poll() is None
                ), f"node exited: {process.args}; see log/test-*"
            rclpy.spin_once(self, timeout_sec=0.01)
            if predicate():
                return
        raise AssertionError("timed out waiting for ROS condition")

    def wait(self, seconds=0.5):
        end = time.monotonic() + seconds
        self.pump(lambda: time.monotonic() > end, seconds + 2)

    def result(self, future, timeout=8.0):
        self.pump(future.done, timeout)
        return future.result()

    def action(self, client, goal, timeout=10.0):
        self.pump(client.server_is_ready)
        handle = self.result(client.send_goal_async(goal))
        assert handle.accepted
        return self.result(handle.get_result_async(), timeout).result

    def stationary(self, state=2):
        m = Stationary()
        m.header.stamp = self.get_clock().now().to_msg()
        m.state = state
        m.confidence = 1.0
        self.pubs["/loonar/stationary"].publish(m)

    def sensors(self, publish_safety=True):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        if not self.feed:
            return
        stamp = self.get_clock().now().to_msg()
        v = self.command.linear.x
        w = self.command.angular.z
        velocities = [(v - w * 0.21 / 2) / 0.098, (v + w * 0.21 / 2) / 0.098]
        self.positions = [a + b * dt for a, b in zip(self.positions, velocities)]
        gyro = Imu()
        gyro.header.stamp = stamp
        gyro.header.frame_id = "imu_link"
        gyro.orientation_covariance[0] = -1.0
        gyro.linear_acceleration_covariance[0] = -1.0
        gyro.angular_velocity.z = w
        self.pubs["/imu/data"].publish(gyro)
        accel = Imu()
        accel.header = gyro.header
        accel.orientation_covariance[0] = -1.0
        accel.angular_velocity_covariance[0] = -1.0
        accel.linear_acceleration.z = 9.81
        self.pubs["/imu/accel"].publish(accel)
        g = Vector3Stamped()
        g.header = gyro.header
        g.vector.z = 9.81
        self.pubs["/imu/gravity"].publish(g)
        wheels = JointState()
        wheels.header.stamp = stamp
        wheels.name = ["left_wheel", "right_wheel"]
        wheels.position = self.positions
        wheels.velocity = velocities
        self.pubs["/wheel_states"].publish(wheels)
        odom = Odometry()
        odom.header.stamp = stamp
        odom.twist.twist.linear.x = v
        self.pubs["/odom/raw"].publish(odom)
        base = BaseState()
        base.header.stamp = stamp
        base.connected = True
        base.auto_selected = getattr(self, "auto_selected", True)
        self.pubs["/loonar/base/state"].publish(base)
        if publish_safety:
            safe = SafetyState()
            safe.header.stamp = stamp
            safe.emergency_stop = self.emergency
            safe.reason = "injected obstacle" if self.emergency else ""
            self.pubs["/loonar/safety/emergency_stop"].publish(safe)

    def cleanup(self):
        for child in self.children:
            child.send_signal(signal.SIGINT)
        for child in self.children:
            try:
                child.wait(3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in self.logs:
            log.close()
        self.destroy_node()


_domain_offset = 0


@pytest.fixture
def h():
    global _domain_offset
    previous_domain = os.environ.get("ROS_DOMAIN_ID", "97")
    _domain_offset += 1
    os.environ["ROS_DOMAIN_ID"] = str((int(previous_domain) + _domain_offset) % 232)
    (ROOT / "log").mkdir(exist_ok=True)
    rclpy.init()
    node = Harness()
    yield node
    node.cleanup()
    rclpy.shutdown()
    os.environ["ROS_DOMAIN_ID"] = previous_domain


def camera_feed(h, source="/loonar/tof", millimeters=False, delivery_delay=0.0):
    pubs = [
        h.create_publisher(cls, source + "/" + name, qos_profile_sensor_data)
        for cls, name in [
            (CameraInfo, "camera_info"),
            (Image, "amplitude"),
            (Image, "depth"),
        ]
    ]

    def feed():
        info = CameraInfo()
        info.header.stamp = (
            h.get_clock().now() - rclpy.duration.Duration(seconds=delivery_delay)
        ).to_msg()
        info.header.frame_id = "tof_optical_frame"
        info.width = 80
        info.height = 64
        info.k = [40.0, 0.0, 40.0, 0.0, 40.0, 32.0, 0.0, 0.0, 1.0]
        info.d = [0.0] * 5
        info.distortion_model = "plumb_bob"
        pubs[0].publish(info)
        for idx, val in (
            (1, 100.0),
            (2, 800.0 if millimeters else getattr(h, "depth_value", 0.8)),
        ):
            m = Image()
            m.header = info.header
            m.width = 80
            m.height = 64
            m.encoding = "16UC1" if millimeters else "32FC1"
            size = 2 if millimeters else 4
            m.step = 80 * size
            m.data = np.full(
                (64, 80), val, dtype="<u2" if millimeters else "<f4"
            ).tobytes()
            pubs[idx].publish(m)

    h.callbacks.append(feed)
    return feed


@pytest.mark.parametrize("delivery_delay", [0.0, 0.15])
def test_adapter_and_stationary_map_planner(h, delivery_delay):
    h.launch("loonar_tof_adapter", "tof_adapter")
    h.launch(
        "loonar_terrain_perception",
        "terrain_perception",
        pixel_stride=1,
        x_max=1.0,
        sensor_timeout=0.5,
    )
    h.launch(
        "loonar_terrain_planner",
        "terrain_planner",
        lookahead_distance=0.5,
        map_max_age=8.0,
    )
    camera_feed(h, "/loonar/tof/input", True, delivery_delay)
    h.callbacks.extend([h.sensors, lambda: h.stationary(0)])
    client = ActionClient(h, Build, "/loonar/build_terrain_map")
    h.pump(client.server_is_ready)
    h.wait(0.6)
    g = Build.Goal()
    g.frame_count = 4
    assert not h.result(client.send_goal_async(g)).accepted
    h.callbacks.pop()
    h.callbacks.append(h.stationary)
    maps = []
    h.create_subscription(TerrainMap, "/terrain/map", maps.append, 1)
    h.wait(0.5)
    result = h.action(client, g)
    assert result.success, result.status
    h.pump(lambda: bool(maps))
    valid = [c for c in maps[-1].cells if not c.unknown]
    assert len(valid) > 100
    assert max(abs(c.elevation) for c in valid) < 0.002
    service = h.create_client(PlanTerrain, "/loonar/plan_terrain")
    h.pump(service.service_is_ready)
    req = PlanTerrain.Request()
    req.map_id = result.map_id
    req.forward_only = True
    decision = h.result(service.call_async(req)).decision
    assert decision.status == decision.OK, decision.reason
    assert 0 < decision.command_distance < decision.safe_distance
    req.map_id += 100
    assert h.result(service.call_async(req)).decision.status != decision.OK


def test_motion_gyro_encoder_cancel_and_emergency(h):
    h.launch(
        "loonar_motion_primitives",
        "motion_primitives",
        enable_motion=True,
        calibration_confirmed=True,
        sensor_timeout=0.5,
    )
    h.callbacks.append(h.sensors)
    client = ActionClient(h, Motion, "/loonar/execute_motion_primitive")
    h.pump(client.server_is_ready)
    h.wait(0.8)
    g = Motion.Goal()
    g.type = 2
    g.target = 0.12
    g.speed = 0.2
    g.timeout = 8.0
    r = h.action(client, g)
    assert r.success, r.termination_reason
    assert abs(r.gyro_delta_yaw - 0.12) < 0.04
    g.type = 1
    g.target = 0.05
    g.speed = 0.08
    r = h.action(client, g)
    assert r.success, r.termination_reason
    assert r.encoder_distance >= 0.04
    g.target = 0.2
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    future = handle.get_result_async()
    h.wait(0.3)
    h.emergency = True
    r = h.result(future).result
    assert not r.success and "safety" in r.termination_reason
    h.wait(0.1)
    assert h.commands[-1] == (0.0, 0.0)
    h.emergency = False
    h.wait(0.2)
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    other = h.result(client.send_goal_async(g))
    assert not other.accepted
    h.result(handle.cancel_goal_async())
    r = h.result(handle.get_result_async()).result
    assert not r.success
    h.wait(0.1)
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    h.feed = False
    r = h.result(handle.get_result_async()).result
    assert not r.success and "stale" in r.termination_reason
    assert h.commands[-1] == (0.0, 0.0)


@pytest.mark.parametrize("delivery_delay", [0.0, 0.15])
def test_stationarity_and_depth_guard(h, delivery_delay):
    h.launch("loonar_motion_primitives", "motion_primitives")
    h.launch("loonar_stationary_detector", "stationary_detector", sensor_timeout=0.5)
    h.launch(
        "loonar_safety_monitor", "safety_monitor", sensor_timeout=0.5, pixel_stride=1
    )
    # Test TF is a downward camera at base z=0.8; axle-level ground is z=-0.098.
    h.depth_value = 0.898
    camera_feed(h, delivery_delay=delivery_delay)
    h.callbacks.append(lambda: h.sensors(False))
    stationary = []
    safety = []
    h.create_subscription(Stationary, "/loonar/stationary", stationary.append, 10)
    h.create_subscription(
        SafetyState, "/loonar/safety/emergency_stop", safety.append, 10
    )
    h.pump(lambda: stationary and stationary[-1].state == 2, 10)
    h.pump(lambda: safety and not safety[-1].emergency_stop, 10)
    h.depth_value = 0.868  # 30 mm relief: no independent emergency stop
    h.wait(0.4)
    assert not safety[-1].emergency_stop
    h.depth_value = 0.65
    h.pump(lambda: safety[-1].emergency_stop and "collision" in safety[-1].reason)
    h.depth_value = 0.898
    h.pump(lambda: not safety[-1].emergency_stop)
    # Stationarity is measured, not inferred from absence of a velocity command.
    h.command.linear.x = 0.1
    h.pump(lambda: stationary[-1].state == 0)
    h.feed = False
    h.pump(lambda: safety[-1].emergency_stop and stationary[-1].state == 3)


def test_sdk_loader_failure_is_diagnostic(h, tmp_path):
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus

    helper = tmp_path / "failed-sdk"
    helper.write_text(
        "#!/bin/sh\necho 'libopencv_core.so.3.4: cannot open shared object file' >&2\nexit 127\n"
    )
    helper.chmod(0o755)
    diagnostics = []
    h.create_subscription(DiagnosticArray, "/diagnostics", diagnostics.append, 10)
    h.launch("loonar_tof_adapter", "tof_adapter", source="sdk", helper=str(helper))
    h.pump(
        lambda: any(
            s.name == "loonar_tof_adapter"
            and s.level == DiagnosticStatus.ERROR
            and "127" in s.message
            and "libopencv_core" in s.message
            for d in diagnostics
            for s in d.status
        )
    )


def test_guard_accepts_axle_relative_height_and_rejects_inversion(h):
    from rclpy.parameter import Parameter
    from rclpy.parameter_client import AsyncParameterClient

    h.launch(
        "loonar_safety_monitor",
        "safety_monitor",
        collision_min_height=-0.03,
        collision_max_height=0.60,
    )
    params = AsyncParameterClient(h, "loonar_safety_monitor")
    h.pump(params.services_are_ready)
    result = h.result(
        params.set_parameters([Parameter("collision_max_height", value=-0.04)])
    )
    assert not result.results[0].successful


def test_planner_short_approach_traversable_step_and_unknown(h):
    h.launch(
        "loonar_terrain_planner",
        "terrain_planner",
        robot_length=0.30,
        robot_width=0.21,
        tail_offset=0.15,
        safety_margin=0.01,
    )
    pub = h.create_publisher(TerrainMap, "/terrain/map", 1)
    client = h.create_client(PlanTerrain, "/loonar/plan_terrain")
    h.pump(lambda: client.service_is_ready() and pub.get_subscription_count() > 0)
    grid = TerrainMap()
    grid.header.frame_id = "base_link"
    grid.map_id = 1
    grid.resolution = 0.025
    grid.x_min = -0.25
    grid.y_min = -0.375
    grid.size_x = 40
    grid.size_y = 30
    for i in range(grid.size_x):
        for j in range(grid.size_y):
            c = TerrainCell()
            c.observed = True
            c.confidence = 1.0
            c.step_up = 0.2 if -0.25 + (i + 0.5) * 0.025 >= 0.35 else 0.0
            grid.cells.append(c)

    def plan():
        grid.header.stamp = h.get_clock().now().to_msg()
        pub.publish(grid)
        h.wait(0.15)
        request = PlanTerrain.Request()
        request.map_id = grid.map_id
        request.forward_only = True
        return h.result(client.call_async(request)).decision

    d = plan()
    assert d.status == d.OK, d.reason
    assert 0.10 <= d.command_distance < 0.15
    assert d.command_distance + 0.07 <= d.safe_distance + 1e-6
    for c in grid.cells:
        c.step_up = c.step_down = 0.03
    grid.map_id += 1
    d = plan()
    assert d.status == d.OK and d.command_distance > 0.15, d.reason
    for c in grid.cells:
        c.unknown = True
    grid.map_id += 1
    d = plan()
    assert d.status == d.NO_SAFE_PATH and d.command_distance == 0
    assert "unknown" in d.reason


def test_motion_accepts_ten_cm_limit_at_wire_precision(h):
    h.launch(
        "loonar_motion_primitives",
        "motion_primitives",
        enable_motion=True,
        calibration_confirmed=True,
        max_drive_distance=0.1,
    )
    h.callbacks.append(h.sensors)
    client = ActionClient(h, Motion, "/loonar/execute_motion_primitive")
    h.pump(client.server_is_ready)
    h.wait(0.4)
    g = Motion.Goal()
    g.type = g.TYPE_STRAIGHT
    g.target = 0.1001
    g.speed = 0.05
    g.timeout = 8.0
    assert not h.result(client.send_goal_async(g)).accepted
    g.target = 0.1
    result = h.action(client, g)
    assert result.success, result.termination_reason
    assert 0.095 <= result.encoder_distance <= 0.105
    assert h.commands[-1] == (0.0, 0.0)


@pytest.mark.parametrize("safe", [True, False])
@pytest.mark.parametrize("gcs_control", [False, True])
def test_navigator_requires_second_capture_before_straight(h, safe, gcs_control):
    events = []
    counter = [0]

    def build(goal):
        counter[0] += 1
        events.append("capture")
        r = Build.Result()
        r.success = True
        r.map_id = counter[0]
        r.valid_ratio = 1.0
        goal.succeed()
        return r

    def motion(goal):
        events.append({0: "stop", 1: "straight", 2: "rotate"}[goal.request.type])
        r = Motion.Result()
        r.success = True
        goal.succeed()
        return r

    def plan(req, res):
        events.append("forward_plan" if req.forward_only else "heading_plan")
        d = TerrainDecision()
        d.header.stamp = h.get_clock().now().to_msg()
        d.map_id = req.map_id
        d.status = d.OK if safe else d.NO_SAFE_PATH
        d.selected_heading = 0.0 if req.forward_only else 0.2
        d.safe_distance = 0.3
        d.command_distance = 0.15
        d.confidence = 1.0
        res.decision = d
        return res

    servers = [
        ActionServer(h, Build, "/loonar/build_terrain_map", build),
        ActionServer(h, Motion, "/loonar/execute_motion_primitive", motion),
    ]
    h.create_service(PlanTerrain, "/loonar/plan_terrain", plan)
    h.create_service(Trigger, "/loonar/motion/stop", lambda req, res: res)
    h.callbacks.extend([h.sensors, h.stationary])
    h.launch(
        "loonar_terrain_navigator",
        "terrain_navigator",
        enable_motion=True,
        calibration_confirmed=True,
        autostart=True,
        gcs_auto_start=gcs_control,
        sensor_timeout=0.5,
        recovery_rotation_clearance_verified=True,
        recovery_max_angle=0.7,
    )
    if gcs_control:
        # Startup in AUTO must not replay a previous session's selection.
        h.pump(lambda: "loonar_terrain_navigator" in h.get_node_names())
        h.wait(0.6)
        assert not events
        h.auto_selected = False
        h.wait(0.3)
        h.auto_selected = True
    if not safe:
        states = []
        h.create_subscription(
            String, "/loonar/navigation/state", lambda m: states.append(m.data), 10
        )
        h.pump(lambda: "SAFE_STOP" in states, 12)
        assert (
            "straight" not in events
            and events.count("rotate") == 2
            and events.count("capture") == 3
        ), events
        for server in servers:
            server.destroy()
        return
    h.pump(lambda: "straight" in events, 12)
    assert events[:6] == [
        "stop",
        "capture",
        "heading_plan",
        "rotate",
        "capture",
        "forward_plan",
    ], events
    assert events[6] == "straight"
    h.emergency = True
    states = []
    h.create_subscription(
        String, "/loonar/navigation/state", lambda m: states.append(m.data), 10
    )
    h.pump(lambda: "SAFE_STOP" in states)
    count = len(events)
    h.wait(0.3)
    assert len(events) == count
    if gcs_control:
        h.emergency = False
        h.wait(0.6)
        assert len(events) == count, "AUTO must not restart after safety clears"
        h.auto_selected = False
        h.wait(0.3)
        h.auto_selected = True
        h.pump(lambda: events.count("straight") >= 2)
        h.auto_selected = False
        h.pump(lambda: states[-1] == "SAFE_STOP")
        count = len(events)
        h.wait(0.3)
        assert len(events) == count, "GCS STOP must cancel navigation"
    for server in servers:
        server.destroy()


def test_base_io_existing_protocol_and_command_watchdog(h, tmp_path):
    import json
    import socket
    import struct

    header = struct.Struct("<IHHI")
    gateway_path = str(tmp_path / "ros.sock")
    sample_path = str(tmp_path / "samples.sock")
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": 2,
                "devices": {
                    "control": {
                        "uid": "0000000000000001",
                        "geometry": {
                            "radius_m": 0.098,
                            "track_m": 0.21,
                            "counts_per_rev": 1000.0,
                            "left_sign": 1,
                            "right_sign": 1,
                        },
                    }
                },
            }
        )
    )
    server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    server.bind(gateway_path)
    server.listen()
    server.setblocking(False)
    source = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    peer = [None]
    seq = [0]
    motion_packets = []
    feed = [True]
    driver_error = [0]

    def gateway():
        if peer[0] is None:
            try:
                peer[0], _ = server.accept()
                peer[0].setblocking(False)
            except BlockingIOError:
                pass
        if peer[0]:
            while True:
                try:
                    raw = peer[0].recv(256)
                except BlockingIOError:
                    break
                if not raw:
                    break
                magic, version, kind, size = header.unpack_from(raw)
                if kind == 1:
                    payload = struct.pack("<BBddB", 1, 0, 0.0, 0.0, 0)
                    peer[0].sendall(
                        header.pack(magic, version, 7, len(payload)) + payload
                    )
                elif kind == 2:
                    motion_packets.append(struct.unpack_from("<Bdd", raw, 12))
        if feed[0] and Path(sample_path).exists():
            seq[0] += 1
            payload = bytearray(64)
            struct.pack_into("<I4i", payload, 0, 67, seq[0], seq[0], 50, 50)
            struct.pack_into("<I", payload, 44, driver_error[0])
            payload[42] = 1
            sample = {
                "role": "control",
                "uid": "0000000000000001",
                "boot": 1,
                "seq": seq[0],
                "kind": 33,
                "stamp_ns": time.time_ns(),
                "payload": payload.hex(),
            }
            source.sendto(json.dumps(sample).encode(), sample_path)

    h.callbacks.append(gateway)
    states = []
    wheels = []
    safety = []
    h.create_subscription(
        SafetyState, "/loonar/safety/emergency_stop", safety.append, 10
    )
    h.launch("loonar_safety_monitor", "safety_monitor")
    h.create_subscription(BaseState, "/loonar/base/state", states.append, 10)
    h.create_subscription(
        JointState, "/wheel_states", wheels.append, qos_profile_sensor_data
    )
    h.launch(
        "loonar_bringup",
        "base_io",
        enable_motion=True,
        registry=str(registry),
        sample_socket=sample_path,
        gateway_socket=gateway_path,
    )
    try:
        h.pump(
            lambda: states
            and states[-1].connected
            and states[-1].auto_selected
            and not states[-1].motor_fault,
            8,
        )
        h.pump(lambda: len(wheels) > 2)
        assert wheels[-1].position[0] > wheels[0].position[0]
        pub = h.create_publisher(Twist, "/cmd_vel", 10)
        h.wait(0.2)
        command = Twist()
        command.linear.x = 0.05
        pub.publish(command)
        h.pump(lambda: any(abs(p[1] - 0.05) < 1e-9 for p in motion_packets))
        h.pump(lambda: motion_packets[-1][1:] == (0.0, 0.0))
        assert sum(abs(p[1] - 0.05) < 1e-9 for p in motion_packets) == 1
        driver_error[0] = 0x02000000
        h.pump(lambda: states[-1].motor_fault and "0x02000000" in states[-1].reason)
        h.pump(
            lambda: safety
            and safety[-1].emergency_stop
            and "0x02000000" in safety[-1].reason
        )
        count = len(motion_packets)
        pub.publish(command)
        h.wait(0.2)
        assert not any(abs(p[1]) > 0 for p in motion_packets[count:])
        feed[0] = False
        h.pump(lambda: not states[-1].connected)
    finally:
        h.callbacks.remove(gateway)
        if peer[0]:
            peer[0].close()
        source.close()
        server.close()


def test_capture_timeout_cancel_stationarity_and_parameter_validation(h):
    from rclpy.parameter import Parameter
    from rclpy.parameter_client import AsyncParameterClient

    h.launch(
        "loonar_terrain_perception",
        "terrain_perception",
        capture_timeout=0.35,
        sensor_timeout=0.5,
    )
    h.callbacks.extend([h.sensors, h.stationary])
    client = ActionClient(h, Build, "/loonar/build_terrain_map")
    h.pump(client.server_is_ready)
    h.wait(0.5)
    parameters = AsyncParameterClient(h, "loonar_terrain_perception")
    h.pump(parameters.services_are_ready)
    invalid = h.result(parameters.set_parameters([Parameter("pixel_stride", value=0)]))
    assert not invalid.results[0].successful
    invalid = h.result(parameters.set_parameters([Parameter("x_min", value=3.0)]))
    assert not invalid.results[0].successful
    g = Build.Goal()
    g.frame_count = 1
    assert not h.result(client.send_goal_async(g)).accepted
    g.frame_count = 4
    result = h.action(client, g)
    assert not result.success and "timeout" in result.status
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    h.result(handle.cancel_goal_async())
    assert not h.result(handle.get_result_async()).result.success
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    h.callbacks[-1] = lambda: h.stationary(0)
    result = h.result(handle.get_result_async()).result
    assert not result.success and "stationari" in result.status


def test_executor_sigterm_publishes_zero_before_context_shutdown(h):
    h.launch(
        "loonar_motion_primitives",
        "motion_primitives",
        enable_motion=True,
        calibration_confirmed=True,
        sensor_timeout=0.5,
    )
    h.callbacks.append(h.sensors)
    client = ActionClient(h, Motion, "/loonar/execute_motion_primitive")
    h.pump(client.server_is_ready)
    h.wait(0.6)
    g = Motion.Goal()
    g.type = 1
    g.target = 0.2
    g.speed = 0.05
    g.timeout = 10.0
    handle = h.result(client.send_goal_async(g))
    assert handle.accepted
    h.pump(lambda: any(v > 0 for v, w in h.commands))
    child = h.children.pop()
    child.send_signal(signal.SIGTERM)
    try:
        h.pump(lambda: h.commands[-1] == (0.0, 0.0))
        assert child.wait(3) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
