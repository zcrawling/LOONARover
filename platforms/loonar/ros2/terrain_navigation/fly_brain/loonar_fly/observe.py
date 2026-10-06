"""Read-only status/measurement CLI; usable in the PC inference container."""
import argparse
import json
from pathlib import Path
import statistics
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from sensor_msgs.msg import JointState
from geometry_msgs.msg import Twist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rclpy.init(args=[])
    node = Node("loonar_fly_observer")
    messages = {name: [] for name in ("input", "result", "status", "brain_status", "terrain")}
    motion = {"commands": [], "wheels": []}
    node.create_subscription(Twist, "/cmd_vel", lambda m: motion["commands"].append(
        dict(at=time.monotonic(), v=m.linear.x, w=m.angular.z)), 1)
    node.create_subscription(JointState, "/wheel_states", lambda m: motion["wheels"].append(
        dict(at=time.monotonic(), name=list(m.name), position=list(m.position), velocity=list(m.velocity))), qos_profile_sensor_data)

    def receive(name, msg):
        data = json.loads(msg.data)
        messages[name].append(data)

    for name in messages:
        node.create_subscription(String, f"/loonar/fly/{name}",
                                 lambda msg, name=name: receive(name, msg),
                                 qos_profile_sensor_data if name in ("input", "terrain") else 1)
    end = time.monotonic() + args.seconds
    next_print = 0
    try:
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)
            if time.monotonic() >= next_print:
                last = messages["result"][-1] if messages["result"] else {}
                state = messages["status"][-1] if messages["status"] else {}
                print(json.dumps({"results": len(messages["result"]), "population_hz": last.get("smoothed_hz"),
                                  "blocked_reason": state.get("blocked_reason"),
                                  "terrain_advisory": state.get("terrain_advisory"),
                                  "avoidance": state.get("avoidance"), "commanded": state.get("commanded"),
                                  "mode": state.get("mode", "waiting")}), flush=True)
                next_print = time.monotonic() + 2
        times = [m["compute_ms"] for m in messages["result"]]
        report = {"duration_seconds": args.seconds,
                  "counts": {name: len(values) for name, values in messages.items()},
                  "camera_frames_available": sum(bool(m.get("camera_available")) for m in messages["input"]),
                  "compute_ms_median": statistics.median(times) if times else None,
                  "compute_ms_max": max(times) if times else None,
                  "last": {name: values[-1] if values else None for name, values in messages.items()},
                  "motion": motion,
                  "status_history": messages["status"],
                  "cmd_vel_publishers": len(node.get_publishers_info_by_topic("/cmd_vel"))}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k not in ("last", "motion", "status_history")}), flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
