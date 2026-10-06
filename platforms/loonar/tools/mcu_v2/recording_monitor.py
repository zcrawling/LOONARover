"""Record stream freshness/counts and disk space; never issue hardware commands."""
import json
import os
from pathlib import Path
import shutil
import sys
import time


class StreamState:
    def __init__(self, names):
        self.streams = {name: dict(count=0, stamp_ns=None, valid=False) for name in names}

    def update(self, name, stamp, valid):
        row = self.streams[name]
        row.update(count=row["count"] + 1, stamp_ns=int(stamp), valid=bool(valid))

    def snapshot(self, now):
        rows = {}
        for name, row in self.streams.items():
            age = (now - row["stamp_ns"]) / 1e9 if row["stamp_ns"] is not None else None
            rows[name] = dict(row, age_s=age,
                              fresh=bool(row["valid"] and age is not None and -0.02 <= age <= 2))
        return rows


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu, PointCloud2, CompressedImage
    from diagnostic_msgs.msg import DiagnosticArray
    from std_msgs.msg import String

    rclpy.init(args=[])
    node = Node("loonar_recording_monitor")
    status_path, bag_dir = map(Path, sys.argv[1:3])
    topics = {
        "/tof/depth/points": (PointCloud2, lambda m: m.width * m.height > 0),
        "/camera/image_raw/compressed": (CompressedImage, lambda m: bool(m.data)),
        "/imu/data": (Imu, lambda m: m.angular_velocity_covariance[0] >= 0),
        "/imu/accel": (Imu, lambda m: m.linear_acceleration_covariance[0] >= 0),
        "/imu/orientation_raw": (Imu, lambda m: m.orientation_covariance[0] >= 0),
        "/motor/feedback": (DiagnosticArray, lambda m: any(
            v.key == "valid_mask" and v.value == "255" for s in m.status for v in s.values)),
    }
    state = StreamState(topics)
    publisher = node.create_publisher(String, "/recording/status", 10)
    subscriptions = []

    def receive(name, check, msg):
        stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        state.update(name, stamp, check(msg))

    for name, (kind, check) in topics.items():
        subscriptions.append(node.create_subscription(
            kind, name, lambda msg, n=name, c=check: receive(n, c, msg), qos_profile_sensor_data))

    def report():
        now = time.time_ns()
        streams = state.snapshot(now)
        missing = [name for name, row in streams.items() if not row["fresh"]]
        free = shutil.disk_usage(bag_dir).free
        payload = dict(stamp_ns=now, clock="PI_CLOCK_REALTIME", streams=streams,
                       missing_or_stale=missing, free_bytes=free,
                       streams_fresh=not missing, low_disk=free < 1024**3,
                       note="Subscriber observations; bag readback is needed to verify stored counts")
        encoded = json.dumps(payload)
        publisher.publish(String(data=encoded))
        temporary = status_path.with_suffix(".tmp")
        temporary.write_text(encoded + "\n")
        os.replace(temporary, status_path)
        print(f"streams={'OK' if not missing else 'MISSING/STALE ' + ', '.join(missing)} "
              f"free={free / 1024**3:.1f}GiB", flush=True)

    node.create_timer(2.0, report)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
