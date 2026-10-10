"""Synthetic ROS sensors -> real 138k brain -> guarded candidate, with no motors.

Run with a dedicated ROS_DOMAIN_ID and a compiled terrain workspace. This test
starts the actual pinned brain subprocess, not a fake inference implementation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import Image
from std_msgs.msg import String
from loonar_msgs.msg import BaseState, SafetyState

from loonar_fly.body_node import Body
from loonar_fly.avoidance import scene_from_points


def main():
    root = Path(__file__).resolve().parents[1]
    log = (root / "log/ros-brain.log").open("w")
    rclpy.init()
    node = Node("fly_replay_test")
    body = Body()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(body)
    pub = node.create_publisher(Image, "/loonar/tof/depth", qos_profile_sensor_data)
    basepub = node.create_publisher(BaseState, "/loonar/base/state", 1)
    safepub = node.create_publisher(SafetyState, "/loonar/safety/emergency_stop", 1)
    terrainpub = node.create_publisher(String, "/loonar/fly/terrain", qos_profile_sensor_data)
    xx, yy = np.meshgrid(np.arange(.16, 1.04, .015), np.arange(-.8, .8, .015))
    floor_scene = scene_from_points(np.column_stack((xx.ravel(), yy.ravel(), np.full(xx.size, -.098))))
    candidates, results, ready = [], [], []
    node.create_subscription(TwistStamped, "/loonar/fly/candidate_cmd_vel", lambda m: candidates.append(m.twist.linear.x), 1)
    node.create_subscription(String, "/loonar/fly/result", lambda m: results.append(json.loads(m.data)), 1)
    node.create_subscription(String, "/loonar/fly/brain_status", lambda m: ready.append(m.data), 1)
    brain = subprocess.Popen([sys.executable, "-m", "loonar_fly.brain_node", "--motivation-hz", "150"],
                             cwd=root, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 150
        while not ready and time.monotonic() < deadline:
            if brain.poll() is not None:
                raise RuntimeError((root / "log/ros-brain.log").read_text())
            executor.spin_once(timeout_sec=.02)
        assert ready, "whole brain not ready"

        def run(seconds, *, fault=False, depth=True, safety=False):
            deadline = time.monotonic() + seconds
            next_pub = 0
            while time.monotonic() < deadline:
                if time.monotonic() >= next_pub:
                    stamp = node.get_clock().now().to_msg()
                    if depth:
                        msg = Image()
                        msg.header.stamp = stamp
                        msg.height, msg.width, msg.step = 16, 24, 96
                        msg.encoding = "32FC1"
                        values = np.ones((16, 24), np.float32)
                        values[:, :12] = .2
                        msg.data = values.tobytes()
                        pub.publish(msg)
                        scene = dict(floor_scene, stamp=stamp.sec+stamp.nanosec*1e-9,
                                     frame_id=f'{stamp.sec}:{stamp.nanosec}')
                        terrainpub.publish(String(data=json.dumps(scene)))
                    base = BaseState(connected=True, motor_fault=fault, auto_selected=True,
                                     reason="RoboClaw 0x02000000" if fault else "healthy replay")
                    base.header.stamp = stamp
                    basepub.publish(base)
                    safe = SafetyState(emergency_stop=safety, reason="test stop" if safety else "clear")
                    safe.header.stamp = stamp
                    safepub.publish(safe)
                    next_pub = time.monotonic() + .05
                executor.spin_once(timeout_sec=.005)

        run(6)
        assert len(results) >= 3, "no sustained full-brain inference"
        assert all(r['input_rates_hz']['LC4_left'] == 0 and r['input_rates_hz']['LC4_right'] == 0
                   for r in results), 'raw close floor must not stimulate obstacle neurons'
        assert any(v > 0 for v in candidates), "no guarded candidate from positive-control P9 stimulation"
        assert not node.get_publishers_info_by_topic("/cmd_vel"), "unexpected physical-command publisher"
        run(1, fault=True)
        assert candidates[-1] == 0
        assert "0x02000000" in body.blocked_reason(time.monotonic())
        run(1, safety=True)
        assert candidates[-1] == 0
        run(1, depth=False)
        assert candidates[-1] == 0
        assert not node.get_publishers_info_by_topic("/cmd_vel")
        report = {"passed": True, "full_brain_results": len(results),
                  "positive_candidate_seen": True, "ground_removed_input_verified": True, "motor_publishers": 0,
                  "fault_zero": True, "safety_zero": True, "stale_depth_zero": True,
                  "compute_ms": [r["compute_ms"] for r in results],
                  "fixture": "synthetic ROS sensors, real pinned whole brain; no hardware"}
        (root / "log/ros-replay.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        brain.terminate()
        try:
            brain.wait(timeout=10)
        except subprocess.TimeoutExpired:
            brain.kill()
            brain.wait()
        executor.shutdown()
        body.destroy_node()
        node.destroy_node()
        rclpy.shutdown()
        log.close()


if __name__ == "__main__":
    main()
