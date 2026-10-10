"""Pi-side shadow body. Deliberately has no /cmd_vel publisher or action client."""
import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import Image, CompressedImage, Imu, JointState
from std_msgs.msg import String
from loonar_msgs.msg import BaseState, SafetyState

from .interface import depth_array, encode_depth, ExpansionEncoder, decode_candidate
from .protocol import Requests
from .avoidance import Avoidance


class Body(Node):
    def __init__(self, sensor_timeout=.3, result_timeout=.75, terrain_input=False):
        super().__init__("loonar_fly_body")
        self.sensor_timeout = sensor_timeout
        self.terrain_input = terrain_input
        self.requests = Requests(ttl=result_timeout)
        self.avoidance = Avoidance()
        self.scene = None
        self.scene_at = None
        self.decision = {}
        self.visual = ExpansionEncoder()
        self.depth = self.depth_at = None
        self.depth_rejection = "no depth received"
        self.partial_depth = False
        self.expansion = {}
        self.camera_at = None
        self.feedback = {}
        self.context_at = {}
        self.base = self.safety = None
        self.base_at = self.safety_at = None
        self.candidate = None
        self.candidate_at = None
        self.inference = {}
        self.results_accepted = 0
        self.results_rejected = 0
        self.last_rejection = ""
        self.input_pub = self.create_publisher(String, "/loonar/fly/input", qos_profile_sensor_data)
        self.candidate_pub = self.create_publisher(TwistStamped, "/loonar/fly/candidate_cmd_vel", 1)
        self.status_pub = self.create_publisher(String, "/loonar/fly/status", 1)
        self.create_subscription(Image, "/loonar/tof/depth", self.on_depth, qos_profile_sensor_data)
        self.create_subscription(CompressedImage, "/camera/image_raw/compressed", self.on_camera, qos_profile_sensor_data)
        self.create_subscription(Imu, "/imu/data", self.on_imu, qos_profile_sensor_data)
        self.create_subscription(JointState, "/wheel_states", self.on_wheels, qos_profile_sensor_data)
        self.create_subscription(BaseState, "/loonar/base/state", self.on_base, 1)
        self.create_subscription(SafetyState, "/loonar/safety/emergency_stop", self.on_safety, 1)
        self.create_subscription(String, "/loonar/fly/result", self.on_result, 1)
        self.create_subscription(String, "/loonar/fly/terrain", self.on_terrain, qos_profile_sensor_data)
        self.create_timer(.1, self.send_input)
        self.create_timer(.05, self.publish_candidate)
        self.create_timer(1., self.publish_status)
        self.get_logger().info("Whole-fly sensor interface initialized")

    def sample_time(self, message):
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        age = self.get_clock().now().nanoseconds * 1e-9 - stamp
        if not math.isfinite(age) or not 0 <= age <= self.sensor_timeout:
            raise ValueError("sensor timestamp stale/future")
        return time.monotonic() - age

    def on_depth(self, msg):
        try:
            at = self.sample_time(msg)
            features = encode_depth(depth_array(msg))
            self.partial_depth = any(features[s]["valid_fraction"] < .25 for s in ("left", "right"))
            if sum(features[s]["valid_fraction"] for s in ("left", "right")) < .02:
                raise ValueError("insufficient depth returns")
            # Check sparse-frame terrain support at use time, so callback order
            # (depth arrives before the matching terrain) cannot discard it.
            self.depth, self.depth_at = features, at
            self.depth_rejection = ""
        except (ValueError, TypeError) as error:
            self.depth = self.depth_at = None
            self.depth_rejection = str(error)

    def on_camera(self, msg):
        try:
            at = self.sample_time(msg)
            self.expansion = self.visual.update(bytes(msg.data), at)
            self.camera_at = at
        except (ValueError, ImportError):
            self.expansion, self.camera_at = {}, None

    def on_terrain(self, msg):
        try:
            if len(msg.data) > 20000:
                raise ValueError("oversized terrain")
            scene = json.loads(msg.data)
            age = self.get_clock().now().nanoseconds*1e-9 - float(scene["stamp"])
            if not math.isfinite(age) or not 0 <= age <= self.sensor_timeout:
                return
            if scene.get("ready"):
                if len(scene["directions"]) != 7:
                    raise ValueError("expected seven terrain directions")
                for ray in scene["directions"]:
                    if not all(math.isfinite(float(ray[k])) for k in (
                        "heading", "clearance_m", "support_until_m", "low_step_m")):
                        raise ValueError("invalid terrain data")
            self.decision = self.avoidance.update(scene, time.monotonic(), scene["frame_id"])
            self.scene, self.scene_at = scene, time.monotonic()-age
        except (ValueError, TypeError, KeyError):
            self.scene, self.scene_at = None, None
            self.decision = {}

    def on_imu(self, msg):
        self.set_context("gyro_rps", msg, [msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z])

    def on_wheels(self, msg):
        self.set_context("wheel_rps", msg, list(msg.velocity))

    def set_context(self, key, msg, values):
        try:
            at = self.sample_time(msg)
            if not values or not all(math.isfinite(v) for v in values):
                raise ValueError("invalid feedback")
            self.feedback[key], self.context_at[key] = values, at
        except ValueError:
            self.feedback.pop(key, None)
            self.context_at.pop(key, None)

    def on_base(self, msg):
        self.base = msg
        try:
            self.base_at = self.sample_time(msg)
        except ValueError:
            self.base_at = None

    def on_safety(self, msg):
        self.safety = msg
        try:
            self.safety_at = self.sample_time(msg)
        except ValueError:
            self.safety_at = None

    def fresh(self, at, now, timeout=None):
        timeout = self.sensor_timeout if timeout is None else timeout
        return at is not None and 0 <= now - at <= timeout

    def send_input(self):
        now = time.monotonic()
        if not self.terrain_input and not self.fresh(self.depth_at, now):
            return
        terrain_ok = self.fresh(self.scene_at, now) and self.scene.get("ready")
        if not terrain_ok or "vision" not in self.scene:
            return
        camera_ok = self.fresh(self.camera_at, now)
        oldest = self.scene_at if self.terrain_input else min(self.depth_at, self.scene_at)
        if camera_ok:
            oldest = min(oldest, self.camera_at)
        packet = self.requests.issue(now, oldest)
        packet.update(vision=self.scene["vision"], expansion=self.expansion if camera_ok else {},
                      camera_available=camera_ok,
                      # Recorded context only: no fabricated mechanosensory mapping.
                      context={key: value for key, value in self.feedback.items()
                               if self.fresh(self.context_at[key], now)})
        packet["avoidance"] = self.decision
        packet["directions"] = self.scene["directions"]
        self.input_pub.publish(String(data=json.dumps(packet, allow_nan=False)))

    def on_result(self, msg):
        try:
            if len(msg.data) > 20000:
                raise ValueError("oversized result")
            result = json.loads(msg.data)
            candidate = decode_candidate(result.get("control_hz", result["smoothed_hz"]))
            at = self.requests.accept(result, time.monotonic())
            self.candidate, self.candidate_at, self.inference = candidate, at, result
            self.results_accepted += 1
        except (ValueError, TypeError, KeyError) as error:
            # A bad result cannot renew the last valid candidate's lifetime.
            self.results_rejected += 1
            self.last_rejection = str(error)

    def blocked_reason(self, now, *, scene_guard=True):
        if not self.fresh(self.base_at, now):
            return "base state expired/unavailable"
        if not self.base.connected or self.base.motor_fault:
            return self.base.reason or "base disconnected/motor fault"
        if scene_guard:
            if not self.fresh(self.safety_at, now):
                return "safety state expired/unavailable"
            if self.safety.emergency_stop:
                return self.safety.reason or "emergency stop"
        if not self.fresh(self.depth_at, now):
            return "depth expired: " + (self.depth_rejection or "stale frame")
        if self.partial_depth and not (self.fresh(self.scene_at, now) and self.scene.get("ready")):
            return "partial depth awaiting calibrated terrain"
        if not self.fresh(self.candidate_at, now, self.requests.ttl):
            return "brain result expired/unavailable"
        return ""

    def publish_candidate(self):
        # Even this topic is guarded, but it MUST NOT be remapped to /cmd_vel:
        # it is not terrain planning, AUTO arbitration or a certified controller.
        now = time.monotonic()
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        if not self.blocked_reason(now):
            msg.twist.linear.x = self.candidate["linear_mps"]
            msg.twist.angular.z = self.candidate["angular_rps"]
        self.candidate_pub.publish(msg)

    def publish_status(self):
        data = {"mode": "shadow", "actuation_enabled": False,
                "blocked_reason": self.blocked_reason(time.monotonic()),
                "results_accepted": self.results_accepted,
                "results_rejected": self.results_rejected,
                "last_rejection": self.last_rejection,
                "candidate": self.candidate, "inference": self.inference}
        self.status_pub.publish(String(data=json.dumps(data, allow_nan=False)))


def main():
    rclpy.init()
    node = Body()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
