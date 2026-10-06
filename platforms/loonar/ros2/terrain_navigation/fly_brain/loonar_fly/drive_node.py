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

from .body_node import Body
from .drive import ModeChannel, DriveGate


class Driver(Body):
    def __init__(self, gateway_socket, max_drive_seconds=0, max_speed=.2):
        super().__init__()
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
        self.get_logger().info(f"FLY AVOIDANCE: <={max_speed} m/s, <=0.6 rad/s; turn/scan/advance; Ctrl+C stops")

    def blocked_reason(self, now):
        # The old aggregate scene monitor remains advisory. The local adapter
        # below actively chooses turns and advancement from current terrain.
        return super().blocked_reason(now, scene_guard=False)

    def on_result(self, msg):
        before = self.results_accepted
        super().on_result(msg)
        if self.results_accepted != before:
            worker = self.inference.get("worker_session")
            if not isinstance(worker, str) or not worker:
                self.gate.halt("brain missing worker identity; update PC code")
            elif self.worker is not None and self.worker != worker:
                self.gate.halt("PC brain restarted; restart Pi command to rearm")
            else:
                self.worker = worker

    def on_halt(self, msg):
        if msg.data == self.worker:
            self.halt("PC Ctrl+C/brain shutdown; restart Pi command to rearm")

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
        if not self.fresh(self.scene_at, now):
            reason = reason or "terrain observations expired/unavailable"
        if self.base is not None and self.base.motor_fault and self.gate.started is not None:
            self.gate.halt("motor fault during drive; restart after resolving fault")
        try:
            if self.mode.socket is not None or now >= self.mode_retry:
                self.mode.connect()
        except OSError as error:
            reason = f"gateway unavailable: {error}"
            self.mode_retry = now + 1
            self.gate.clear_since = None
        if self.mode.socket is None:
            reason = reason or "gateway unavailable"
        adapted = self.avoidance.command(self.candidate, self.decision) if self.candidate else None
        enabled, v, w = self.gate.evaluate(now, reason, adapted)
        command = Twist()
        try:
            if enabled and not self.stopping:
                self.mode.select_auto()
                # Wait for base_io's acknowledgement before a nonzero command.
                if self.base.auto_selected:
                    command.linear.x, command.angular.z = v, w
            elif self.mode.auto:
                self.mode.stop()
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
            "terrain_advisory": self.safety.reason if self.safety else "unavailable",
            "terrain_advisory_fresh": self.fresh(self.safety_at, time.monotonic()),
            "blocked_reason": self.gate.reason, "latched_stop": self.gate.latched,
            "auto_selected": self.mode.auto, "candidate": self.candidate,
            "commanded": self.commanded,
            "results_accepted": self.results_accepted, "results_rejected": self.results_rejected,
            "last_rejection": self.last_rejection, "inference": self.inference}, allow_nan=False)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-socket", type=Path, required=True)
    parser.add_argument("--max-drive-seconds", type=float, default=0)
    parser.add_argument("--max-speed", type=float, default=.2)
    args = parser.parse_args()
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    node = Driver(args.gateway_socket, args.max_drive_seconds, args.max_speed)

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
