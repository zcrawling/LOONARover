"""Pi hardware acceptance: real ToF + CAD TF, motion disabled, no MCU connection."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformListener


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("params_file")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = Node("tof_cad_acceptance")
    tf = Buffer()
    listener = TransformListener(tf, node)
    messages = {"depth": [], "amplitude": [], "camera_info": []}
    diagnostic = []
    subscriptions = [
        node.create_subscription(
            cls, "/loonar/tof/" + key, messages[key].append, qos_profile_sensor_data
        )
        for key, cls in (
            ("depth", Image),
            ("amplitude", Image),
            ("camera_info", CameraInfo),
        )
    ]
    subscriptions.append(
        node.create_subscription(DiagnosticArray, "/diagnostics", diagnostic.append, 10)
    )
    log = args.output.with_suffix(".log").open("w")
    child = subprocess.Popen(
        [
            "ros2",
            "launch",
            "loonar_bringup",
            "terrain.launch.py",
            "params_file:=" + args.params_file,
            "publish_tf:=true",
            "run_base_io:=false",
            "enable_motion:=false",
            "calibration_confirmed:=false",
            "autostart:=false",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    report = {}
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            assert child.poll() is None, "launch terminated early"
            rclpy.spin_once(node, timeout_sec=0.05)
        report["received"] = {key: len(value) for key, value in messages.items()}
        assert all(len(v) >= 30 for v in messages.values()), report
        depth = messages["depth"][-1]
        pixels = np.frombuffer(depth.data, dtype="<f4")
        valid = pixels[np.isfinite(pixels)]
        report.update(
            width=depth.width,
            height=depth.height,
            encoding=depth.encoding,
            valid_ratio=float(len(valid) / len(pixels)),
            range_m=[float(valid.min()), float(valid.max())] if len(valid) else [],
            frame_id=depth.header.frame_id,
        )
        assert depth.encoding == "32FC1" and len(valid) > 0

        def stamps(items):
            return {m.header.stamp.sec * 10**9 + m.header.stamp.nanosec for m in items}

        paired = (
            stamps(messages["depth"])
            & stamps(messages["amplitude"])
            & stamps(messages["camera_info"])
        )
        report["matched_stamps"] = len(paired)
        assert len(paired) >= 30
        report["tf"] = {}
        for frame in ("imu_link", "tof_optical_frame"):
            t = tf.lookup_transform("base_link", frame, rclpy.time.Time()).transform
            report["tf"][frame] = dict(
                xyz=[t.translation.x, t.translation.y, t.translation.z],
                quaternion_xyzw=[
                    t.rotation.x,
                    t.rotation.y,
                    t.rotation.z,
                    t.rotation.w,
                ],
            )
        np.testing.assert_allclose(
            report["tf"]["tof_optical_frame"]["xyz"],
            [0.03575, 0.00005, -0.0075],
            atol=1e-8,
        )
        np.testing.assert_allclose(
            report["tf"]["imu_link"]["quaternion_xyzw"],
            [0, 0, 2**-0.5, 2**-0.5],
            atol=1e-8,
        )
        sdk = [
            s for d in diagnostic for s in d.status if s.name == "loonar_tof_adapter"
        ]
        report["sdk_diagnostic"] = sdk[-1].message if sdk else "missing"
        assert sdk and sdk[-1].level == b"\x00", report["sdk_diagnostic"]
        report["passed"] = True
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        report["launch_exit"] = child.returncode
        report["motion_enabled"] = False
        report["mcu_connected_by_test"] = False
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        log.close()
        node.destroy_node()
        rclpy.shutdown()
    assert report.get("passed") and child.returncode == 0


if __name__ == "__main__":
    main()
