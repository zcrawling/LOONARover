#!/usr/bin/env python3
"""Observe ToF PointCloud2 for ten seconds; send no commands to the rover."""
import json
import time

import numpy as np
import rclpy
from rclpy.qos import QoSProfile
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2


def main():
    rclpy.init()
    node = rclpy.create_node('loonar_check_tof')
    samples = []
    errors = []

    def receive(msg):
        try:
            xyz = point_cloud2.read_points_numpy(msg, field_names=('x', 'y', 'z'))
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            samples.append((time.monotonic(), stamp, len(xyz), time.time() - stamp))
            if msg.header.frame_id != 'cubeeye_optical' or not np.isfinite(xyz).all():
                errors.append('Unexpected frame or non-finite XYZ')
        except Exception as exc:
            errors.append(str(exc))

    node.create_subscription(PointCloud2, '/tof/depth/points', receive, QoSProfile(depth=20))
    deadline = time.monotonic() + 10
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    progressing = len(samples) >= 2 and all(b[1] > a[1] for a, b in zip(samples, samples[1:]))
    ok = progressing and all(s[2] > 0 and -0.1 <= s[3] < 2 for s in samples) and not errors
    report = {'ok': ok, 'frames': len(samples), 'errors': errors}
    if len(samples) >= 2:
        report.update(hz=(len(samples)-1)/(samples[-1][0]-samples[0][0]),
                      points_min=min(s[2] for s in samples), points_max=max(s[2] for s in samples),
                      max_callback_age_ms=max(s[3] for s in samples)*1000)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
