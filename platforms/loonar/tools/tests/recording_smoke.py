"""Jazzy + GStreamer integration: synthetic inputs -> production bridges -> MCAP.

Run in an isolated ROS domain/container. Opens no device and sends no commands.
Requires rosbag2_storage_mcap, Python GI and GStreamer good/bad/ugly plugins.
"""
import collections
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

import rclpy
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from sensor_msgs.msg import PointCloud2, PointField
import rosbag2_py

ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "platforms/loonar/tools"


def main():
    work = Path(tempfile.mkdtemp(prefix="loonar-bag-smoke-"))
    env = dict(os.environ, PYTHONPATH=str(TOOLS) + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONDONTWRITEBYTECODE="1")
    registry = work / "registry.json"
    registry.write_text(json.dumps({"schema": 2, "devices": {"control": {
        "uid": "0000000000000001", "device": "/dev/serial/by-id/TEST_ONLY",
        "transport": "usb", "geometry": {"radius_m": .098, "track_m": .210,
          "counts_per_rev": 485681, "left_sign": 1, "right_sign": 1}}}}))
    config = work / "video.env"
    config.write_text("VIDEO_SOURCE=libcamera\nVIDEO_PROFILE=low\nGROUND_STATION_IP=127.0.0.1\nVIDEO_PORT=59990\n")
    # Exercise the real shared video/vision/TS/JPEG pipeline, replacing only camera acquisition.
    video_env = dict(env, LOONAR_VIDEO_CONFIG=str(config), LOONAR_VIDEO_DRY_RUN="1",
                     CAMERA_ROS_ENABLED="1", VISION_ENABLED="1",
                     VISION_SOCKET=str(work / "vision.sock"),
                     VIDEO_RECORD_PATH=str(work / "camera with spaces.ts"))
    command = subprocess.check_output(["bash", str(ROOT / "common/video/loonar-video-stream")],
                                      env=video_env, text=True)
    pipeline = shlex.split(command)[2:]
    index = pipeline.index("libcamerasrc")
    pipeline[index:index+1] = ["videotestsrc", "is-live=true"]
    children, logs = [], []

    def start(name, cmd):
        log = open(work / (name + ".log"), "w")
        logs.append(log)
        child = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        children.append(child)
        return child

    def stop(child):
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait(timeout=15)

    rclpy.init()
    node = rclpy.create_node("synthetic_tof_for_bag_test")
    tof = node.create_publisher(PointCloud2, "/tof/depth/points", 10)
    sender = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sample_path = work / "samples.sock"
    sequence = 0

    def send(kind, payload, stamp=None):
        nonlocal sequence
        sequence += 1
        stamp = time.time_ns() if stamp is None else stamp
        raw = dict(role="control", uid="0000000000000001", boot=1, seq=sequence,
                   kind=kind, stamp_ns=stamp, mcu_stamp_us=123456,
                   clock_offset_ns=stamp - 123456000, sync_rtt_ns=1000000,
                   payload=payload.hex())
        sender.sendto(json.dumps(raw).encode(), str(sample_path))

    motor = bytearray(64)
    struct.pack_into("<I6i4h3H", motor, 0, 255, 100, 200, 300, 400, 500, 600,
                     125, 250, -1000, 2000, 241, 51, 360)
    struct.pack_into("<5I", motor, 44, 0, 5, 0, 10, 5)
    try:
        recorder = start("bag", ["bash", str(TOOLS / "record-drive.sh"), str(work / "bag")])
        start("bridge", [sys.executable, "-m", "mcu_v2.ros_bridge", "--ros-args",
              "-p", f"registry:={registry}", "-p", f"socket:={sample_path}"])
        start("camera", [sys.executable, str(ROOT / "common/video/camera_ros.py"), *pipeline])
        start("monitor", [sys.executable, "-m", "mcu_v2.recording_monitor", str(work / "status.json"), str(work)])
        deadline = time.monotonic() + 10
        while not sample_path.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert sample_path.exists(), "ROS bridge did not bind sample socket"
        end = time.monotonic() + 12
        fresh_seen = False
        while time.monotonic() < end:
            assert all(c.poll() is None for c in children), [(log.name, c.poll()) for log, c in zip(logs, children)]
            stamp = time.time_ns()
            msg = PointCloud2()
            msg.header.frame_id = "cubeeye_optical"
            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
            msg.height, msg.width, msg.point_step, msg.row_step = 1, 1, 12, 12
            msg.fields = [PointField(name=n, offset=i*4, datatype=PointField.FLOAT32, count=1)
                          for i, n in enumerate("xyz")]
            msg.data = struct.pack("<3f", 0., 0., 1.)
            tof.publish(msg)
            for sensor in (1, 2, 5):
                send(32, struct.pack("<4BQ5fI", sensor, 3, 1, 0, 123456,
                                    0., 0., 0., 1., 0., 0))
            send(33, motor)
            rclpy.spin_once(node, timeout_sec=.05)
            status_file = work / "status.json"
            if status_file.exists():
                fresh_seen |= json.loads(status_file.read_text())["streams_fresh"]
        assert fresh_seen, "monitor never saw all six required streams fresh"
        old_stamp = time.time_ns() - 10_000_000_000
        send(33, motor, old_stamp)
        time.sleep(5)  # Frozen MCU/ToF must become stale while camera remains live.
        status = json.loads((work / "status.json").read_text())
        assert "/tof/depth/points" in status["missing_or_stale"]
        assert "/camera/image_raw/compressed" not in status["missing_or_stale"]
        for child in reversed(children[1:]):
            stop(child)
        stop(recorder)
        assert recorder.returncode == 0, "recorder did not finish cleanly"
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(work / "bag"), storage_id="mcap"),
                    rosbag2_py.ConverterOptions("", ""))
        types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
        counts = collections.Counter()
        old_raw = old_motor = old_odom = False
        while reader.has_next():
            topic, data, received = reader.read_next()
            msg = deserialize_message(data, types[topic])
            counts[topic] += 1
            if topic == "/camera/image_raw/compressed":
                assert bytes(msg.data[:2]) == b"\xff\xd8", "not JPEG"
                stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
                assert -20_000_000 < received - stamp < 2_000_000_000, "camera clock mismatch"
            if topic == "/camera/timing":
                timing = json.loads(msg.data)
                assert timing["timestamp_source"] == "GST_PTS_MAPPED_TO_PI_REALTIME"
            if topic == "/motor/feedback":
                values = {v.key: v.value for v in msg.status[0].values}
                assert values["left_current_a"] == "1.25" and values["main_voltage_v"] == "24.1"
                old_motor |= msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec == old_stamp
            if topic == "/mcu/control/raw":
                sample = json.loads(msg.data)
                assert sample["sync_rtt_ns"] == 1000000
                assert sample["stamp_ns"] == sample["mcu_stamp_us"] * 1000 + sample["clock_offset_ns"]
                old_raw |= sample["stamp_ns"] == old_stamp
            if topic == "/wheel/odom":
                old_odom |= msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec == old_stamp - 5_000_000
        for topic in ("/tof/depth/points", "/camera/image_raw/compressed", "/camera/timing",
                      "/imu/data", "/imu/accel", "/imu/orientation_raw", "/wheel/odom",
                      "/motor/feedback", "/mcu/control/raw", "/recording/status"):
            assert counts[topic] >= 3, (topic, counts[topic])
        assert old_raw and old_motor and not old_odom, "archive/live freshness separation failed"
        assert (work / "camera with spaces.ts").stat().st_size > 0
        print(json.dumps(dict(result="PASS", work=str(work), messages=counts), indent=2))
    finally:
        for child in reversed(children):
            if child.poll() is None:
                stop(child)
        for log in logs:
            log.close()
        sender.close()
        node.destroy_node()
        rclpy.shutdown()
        print(f"Logs and bag: {work}")


if __name__ == "__main__":
    main()
