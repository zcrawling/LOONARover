"""Smoke-test packaged launch/YAML/URDF and graceful shutdown without hardware."""

import os
import argparse
from pathlib import Path
import signal
import subprocess
import time
import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener

root = Path(__file__).resolve().parents[1]
expected = {
    "loonar_tof_adapter",
    "loonar_stationary_detector",
    "loonar_terrain_perception",
    "loonar_terrain_planner",
    "loonar_motion_primitives",
    "loonar_terrain_navigator",
    "loonar_safety_monitor",
    "robot_state_publisher",
}
if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--tof-only", action="store_true",
                        help="Check adapter and TF without unrelated planner dependencies")
    args = parser.parse_args()
    extra_args = []
    if args.tof_only:
        expected = {"loonar_tof_adapter", "robot_state_publisher"}
        extra_args = [f"run_{name}:=false" for name in
                      ("stationary", "perception", "planner", "motion", "navigator", "safety")]
    rclpy.init()
    observer = Node("terrain_launch_observer")
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, observer)
    log_path = root / "log" / "launch-smoke.log"
    with log_path.open("w") as output:
        child = subprocess.Popen(
            [
                "ros2",
                "launch",
                "loonar_bringup",
                "terrain.launch.py",
                "publish_tf:=true",
            ] + extra_args,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while not expected.issubset(set(observer.get_node_names())):
                assert child.poll() is None, "launch exited during startup"
                assert time.monotonic() < deadline, "nodes did not become ready"
                rclpy.spin_once(observer, timeout_sec=0.1)
            while not all(
                tf_buffer.can_transform("base_link", frame, rclpy.time.Time())
                for frame in ("imu_link", "tof_optical_frame")
            ):
                assert time.monotonic() < deadline, "CAD sensor TF missing"
                rclpy.spin_once(observer, timeout_sec=0.1)
            imu = tf_buffer.lookup_transform(
                "base_link", "imu_link", rclpy.time.Time()
            ).transform
            tof = tf_buffer.lookup_transform(
                "base_link", "tof_optical_frame", rclpy.time.Time()
            ).transform
            assert (
                abs(imu.rotation.z - 2**-0.5) < 1e-8
            ), "IMU CAD yaw must be +90 degrees"
            assert abs(tof.translation.x - 0.05174) < 1e-8
            assert abs(tof.translation.z + 0.0075) < 1e-8
            # Optical image-right = base up; depth = base forward.
            assert abs(abs(tof.rotation.x) - 2**-0.5) < 1e-8
            assert abs(abs(tof.rotation.z) - 2**-0.5) < 1e-8
            assert abs(tof.rotation.y) < 1e-8 and abs(tof.rotation.w) < 1e-8
            child.send_signal(signal.SIGINT)
            assert child.wait(timeout=15) == 0, "launch did not shut down cleanly"
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            observer.destroy_node()
            rclpy.shutdown()
    log = log_path.read_text()
    assert "Traceback" not in log and "process has died" not in log, log
    print(f"{len(expected)} launched nodes, CAD IMU/ToF TF, packaged YAML, clean shutdown: PASS")
