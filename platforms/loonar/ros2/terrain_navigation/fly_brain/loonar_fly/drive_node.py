"""Operator-supervised drive with local terrain turn/advance adaptation."""
import argparse
import json
from pathlib import Path
import signal
import time

import rclpy
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from sensor_msgs.msg import Imu
from rclpy.qos import qos_profile_sensor_data
from .heading import HeadingGoal, yaw_from_quaternion

from .body_node import Body
from .drive import ModeChannel, DriveGate


class Driver(Body):
    def __init__(self, gateway_socket, max_drive_seconds=0, max_speed=.2, external_mode=False, heading_target=None):
        # Oct 9 bag: terrain age median .36s, p90 .50s. Use one
        # terrain freshness check, not a second raw-depth/sparsity veto.
        super().__init__(sensor_timeout=1.0, result_timeout=1.5, terrain_input=True)
        self.external_mode = external_mode
        self.heading = HeadingGoal(heading_target)
        self.heading_at = None
        self.create_subscription(Imu, "/imu/orientation_raw", self.on_heading, qos_profile_sensor_data)
        self.mode = ModeChannel(gateway_socket)
        self.gate = DriveGate(settle_seconds=0, max_drive_seconds=max_drive_seconds, max_speed=max_speed)
        self.motor_pub = self.create_publisher(Twist, "/cmd_vel", 1)
        self.worker = None
        self.stopping = False
        self.mode_retry = 0.0
        self.last_reason = None
        self.commanded = dict(linear_mps=0., angular_rps=0.)
        self.next_reason_log = 0.0
        self.create_subscription(String, "/loonar/fly/halt", self.on_halt, 1)
        self.get_logger().info(f"FLY AVOIDANCE: <={max_speed} m/s, <=0.4 rad/s; measured-obstacle avoidance; Ctrl+C stops")

    def on_heading(self, msg):
        try:
            yaw = yaw_from_quaternion(msg.orientation)
            self.heading_at = self.sample_time(msg)
            self.heading.observe(yaw)
        except ValueError:
            pass

    def blocked_reason(self, now):
        if self.external_mode and self.base is not None and not self.base.auto_selected:
            return "GCS AUTO not selected"
        if not self.fresh(self.base_at, now):
            return "base state expired/unavailable"
        if not self.base.connected or self.base.motor_fault:
            return self.base.reason or "base disconnected/motor fault"
        if not self.fresh(self.scene_at, now) or not self.scene.get("ready"):
            return "terrain observations expired/unavailable"
        if not self.fresh(self.candidate_at, now, self.requests.ttl):
            return "brain result expired/unavailable"
        return ""

    def on_result(self, msg):
        before = self.results_accepted
        super().on_result(msg)
        if self.results_accepted != before:
            worker = self.inference.get("worker_session")
            if isinstance(worker, str) and worker:
                self.worker = worker

    def on_halt(self, msg):
        if msg.data == self.worker:
            self.halt("PC Ctrl+C/brain shutdown; STOP then AUTO to rearm in GCS mode")

    def halt(self, reason):
        self.gate.halt(reason)
        self.mode.stop()  # independent of ROS executor and image callbacks
        if rclpy.ok():
            self.motor_pub.publish(Twist())

    def publish_candidate(self):
        super().publish_candidate()
        if not hasattr(self, "mode"):
            return
        now = time.monotonic()
        reason = self.blocked_reason(now)
        try:
            if not self.external_mode and (self.mode.socket is not None or now >= self.mode_retry):
                self.mode.connect()
        except OSError as error:
            reason = f"gateway unavailable: {error}"
            self.mode_retry = now + 1
            self.gate.clear_since = None
        if not self.external_mode and self.mode.socket is None:
            reason = reason or "gateway unavailable"
        adapted = self.avoidance.command(self.candidate, self.decision) if self.candidate else None
        if adapted is not None and self.fresh(self.heading_at, now):
            adapted = self.heading.command(adapted, self.decision)
        enabled, v, w = self.gate.evaluate(now, reason, adapted)
        command = Twist()
        try:
            if enabled and not self.stopping:
                if not self.external_mode:
                    self.mode.select_auto()
                # Wait for base_io's acknowledgement before a nonzero command.
                if self.base.auto_selected:
                    command.linear.x, command.angular.z = v, w
            elif self.mode.auto and (self.stopping or self.gate.latched):
                self.mode.stop()
            # Temporary data gaps publish zero without AUTO/STOP handshake
            # churn. Fresh data resumes through the existing command watchdog.
        except OSError:
            self.mode.close()
            self.gate.clear_since = None
            command = Twist()
        self.motor_pub.publish(command)
        self.commanded = dict(linear_mps=command.linear.x, angular_rps=command.angular.z)
        reason = self.gate.reason or f"{self.decision.get('mode')}: {self.decision.get('reason')}"
        if reason != self.last_reason and now >= self.next_reason_log:
            self.get_logger().info(reason)
            self.last_reason = reason
            self.next_reason_log = now + 1.0

    def publish_status(self):
        if not hasattr(self, "gate"):
            return
        self.status_pub.publish(String(data=json.dumps({
            "mode": "drive", "actuation_enabled": True,
            "scene_guard_enabled": False,
            "avoidance_enabled": True, "avoidance": self.decision,
            "terrain": self.scene,
            "sensor_timeout_s": self.sensor_timeout, "result_timeout_s": self.requests.ttl,
            "terrain_age_s": time.monotonic()-self.scene_at if self.scene_at is not None else None,
            "terrain_advisory": self.safety.reason if self.safety else "unavailable",
            "terrain_advisory_fresh": self.fresh(self.safety_at, time.monotonic()),
            "blocked_reason": self.gate.reason, "latched_stop": self.gate.latched,
            "external_mode": self.external_mode, "heading": self.heading.status(),
            "auto_selected": self.base.auto_selected if self.external_mode and self.base is not None else self.mode.auto, "candidate": self.candidate,
            "commanded": self.commanded,
            "results_accepted": self.results_accepted, "results_rejected": self.results_rejected,
            "last_rejection": self.last_rejection, "inference": self.inference}, allow_nan=False)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-socket", type=Path, default=Path("/tmp/unused-fly-mode.sock"))
    parser.add_argument("--external-mode", action="store_true")
    parser.add_argument("--heading-target", type=float)
    parser.add_argument("--max-drive-seconds", type=float, default=0)
    parser.add_argument("--max-speed", type=float, default=.2)
    args = parser.parse_args()
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    node = Driver(args.gateway_socket, args.max_drive_seconds, args.max_speed, args.external_mode, args.heading_target)

    def stop(*_):
        node.stopping = True
        node.halt("terminal interrupted; stopped")

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        while rclpy.ok() and not node.stopping:
            rclpy.spin_once(node, timeout_sec=.02)
    finally:
        node.halt("driver shutdown")
        node.mode.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
