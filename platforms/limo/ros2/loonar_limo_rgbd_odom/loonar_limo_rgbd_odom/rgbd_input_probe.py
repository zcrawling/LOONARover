#!/usr/bin/env python3
"""Observe RGB-D input health without modifying, gating, or republishing data."""

import math
import struct
import time
from dataclasses import dataclass
from typing import Optional

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


def stamp_seconds(message) -> float:
    return message.header.stamp.sec + message.header.stamp.nanosec * 1e-9


@dataclass
class ImageState:
    message: Image
    received_s: float


class RgbdInputProbe(Node):
    """Publish transparent diagnostics for RTAB-Map's three required inputs."""

    def __init__(self):
        super().__init__("rgbd_input_probe")
        rgb_topic = self.declare_parameter("rgb_topic", "/tof/color/image_raw").value
        depth_topic = self.declare_parameter("depth_topic", "/tof/depth/image_raw").value
        info_topic = self.declare_parameter("camera_info_topic", "/tof/color/camera_info").value
        self.max_stamp_delta_s = float(self.declare_parameter("max_stamp_delta_s", 0.05).value)
        self.min_valid_depth_ratio = float(
            self.declare_parameter("min_valid_depth_ratio", 0.20).value
        )
        self.rgb: Optional[ImageState] = None
        self.depth: Optional[ImageState] = None
        self.camera_info: Optional[CameraInfo] = None
        self.rgb_count = 0
        self.depth_count = 0
        self.last_rgb_count = 0
        self.last_depth_count = 0
        self.last_tick_s = time.monotonic()

        self.create_subscription(Image, rgb_topic, self._on_rgb, qos_profile_sensor_data)
        self.create_subscription(Image, depth_topic, self._on_depth, qos_profile_sensor_data)
        self.create_subscription(CameraInfo, info_topic, self._on_info, qos_profile_sensor_data)
        self.publisher = self.create_publisher(DiagnosticArray, "/rgbd/input_diagnostics", 10)
        self.create_timer(1.0, self._publish)

    def _on_rgb(self, message: Image):
        self.rgb = ImageState(message, time.monotonic())
        self.rgb_count += 1

    def _on_depth(self, message: Image):
        self.depth = ImageState(message, time.monotonic())
        self.depth_count += 1

    def _on_info(self, message: CameraInfo):
        self.camera_info = message

    @staticmethod
    def _valid_depth_ratio(message: Image) -> float:
        """Sample at most about 20k pixels, respecting row padding."""
        if message.width == 0 or message.height == 0:
            return 0.0
        stride = max(1, (message.width * message.height) // 20000)
        valid = 0
        total = 0
        if message.encoding in ("16UC1", "mono16"):
            byte_order = ">" if message.is_bigendian else "<"
            for index in range(0, message.width * message.height, stride):
                row, column = divmod(index, message.width)
                offset = row * message.step + column * 2
                if offset + 2 <= len(message.data):
                    value = struct.unpack_from(byte_order + "H", message.data, offset)[0]
                    valid += int(value > 0)
                    total += 1
        elif message.encoding == "32FC1":
            byte_order = ">" if message.is_bigendian else "<"
            for index in range(0, message.width * message.height, stride):
                row, column = divmod(index, message.width)
                offset = row * message.step + column * 4
                if offset + 4 <= len(message.data):
                    value = struct.unpack_from(byte_order + "f", message.data, offset)[0]
                    valid += int(math.isfinite(value) and value > 0.0)
                    total += 1
        return valid / total if total else 0.0

    @staticmethod
    def _kv(key: str, value) -> KeyValue:
        return KeyValue(key=key, value=str(value))

    def _publish(self):
        now = time.monotonic()
        elapsed = max(now - self.last_tick_s, 1e-6)
        rgb_hz = (self.rgb_count - self.last_rgb_count) / elapsed
        depth_hz = (self.depth_count - self.last_depth_count) / elapsed
        self.last_tick_s = now
        self.last_rgb_count = self.rgb_count
        self.last_depth_count = self.depth_count

        level = DiagnosticStatus.OK
        messages = []
        values = [self._kv("rgb_hz", f"{rgb_hz:.2f}"), self._kv("depth_hz", f"{depth_hz:.2f}")]
        if self.rgb is None or self.depth is None or self.camera_info is None:
            level = DiagnosticStatus.ERROR
            messages.append("missing RGB, depth, or color CameraInfo")
        else:
            rgb = self.rgb.message
            depth = self.depth.message
            stamp_delta = abs(stamp_seconds(rgb) - stamp_seconds(depth))
            valid_ratio = self._valid_depth_ratio(depth)
            same_size = rgb.width == depth.width and rgb.height == depth.height
            same_frame = rgb.header.frame_id == depth.header.frame_id
            intrinsics_valid = len(self.camera_info.k) == 9 and self.camera_info.k[0] > 0.0 \
                and self.camera_info.k[4] > 0.0
            values.extend([
                self._kv("rgb_size", f"{rgb.width}x{rgb.height}"),
                self._kv("depth_size", f"{depth.width}x{depth.height}"),
                self._kv("rgb_encoding", rgb.encoding),
                self._kv("depth_encoding", depth.encoding),
                self._kv("rgb_frame", rgb.header.frame_id),
                self._kv("depth_frame", depth.header.frame_id),
                self._kv("stamp_delta_s", f"{stamp_delta:.6f}"),
                self._kv("valid_depth_ratio", f"{valid_ratio:.3f}"),
                self._kv("color_intrinsics_valid", intrinsics_valid),
            ])
            if not same_size:
                level = DiagnosticStatus.ERROR
                messages.append("RGB/depth dimensions differ; depth is not registered/cropped")
            if not same_frame:
                level = DiagnosticStatus.ERROR
                messages.append("RGB/depth frame_id differs; depth registration is not proven")
            if stamp_delta > self.max_stamp_delta_s:
                level = max(level, DiagnosticStatus.WARN)
                messages.append("RGB/depth timestamp delta exceeds limit")
            if valid_ratio < self.min_valid_depth_ratio:
                level = max(level, DiagnosticStatus.WARN)
                messages.append("too few valid depth pixels")
            if not intrinsics_valid:
                level = DiagnosticStatus.ERROR
                messages.append("color CameraInfo intrinsics are invalid")
            if now - self.rgb.received_s > 1.0 or now - self.depth.received_s > 1.0:
                level = DiagnosticStatus.ERROR
                messages.append("image stream is stale")

        status = DiagnosticStatus(
            level=level,
            name="loonar_limo_rgbd_odom: input contract",
            message="; ".join(messages) if messages else "RGB-D input contract satisfied",
            hardware_id="orbbec_dabai",
            values=values,
        )
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status]
        self.publisher.publish(array)
        self.get_logger().info(
            f"{status.message} | RGB {rgb_hz:.1f} Hz, depth {depth_hz:.1f} Hz"
        )


def main(args=None):
    rclpy.init(args=args)
    node = RgbdInputProbe()
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
