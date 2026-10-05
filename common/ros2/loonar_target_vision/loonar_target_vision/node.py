"""Read the camera owner's shared RGB frame; publish visual cues only.

The shared-memory PTS is not claimed to be optical capture time. This node
reports host receive and processing age, leaving optical latency to field test.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
from pathlib import Path

from .contract import class_mapping, cue_from_detections, make_detection, model_sha256


def main():
    import gi
    import numpy as np
    import rclpy
    from std_msgs.msg import String

    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gst, GstApp, GstVideo
    from rclpy.node import Node

    Gst.init(None)

    class VisionNode(Node):
        def __init__(self):
            super().__init__("loonar_target_vision")
            defaults = {
                "source_width": 640, "source_height": 360, "source_fps": 10,
                "vision_socket": "/run/loonar/vision.sock",
                "model_path": "/var/lib/loonar/vision/best.pt",
                "model_sha256": "", "input_height": 640, "input_width": 384,
                "confidence": 0.35, "max_result_age_ms": 500.0,
                "cpu_threads": 2,
                "ground_station_ip": "10.42.0.1", "udp_port": 5601,
            }
            for name, value in defaults.items():
                self.declare_parameter(name, value)
            self.cfg = {name: self.get_parameter(name).value for name in defaults}
            width, height, fps = (int(self.cfg[key]) for key in
                                  ("source_width", "source_height", "source_fps"))
            if min(width, height, fps, int(self.cfg["input_height"]),
                   int(self.cfg["input_width"])) <= 0:
                raise ValueError("video and model dimensions must be positive")
            if int(self.cfg["cpu_threads"]) not in range(1, 5):
                raise ValueError("cpu_threads must be between 1 and 4")
            if int(self.cfg["udp_port"]) not in range(1, 65536):
                raise ValueError("invalid UDP port")
            ipaddress.IPv4Address(str(self.cfg["ground_station_ip"]))
            self.destination = (str(self.cfg["ground_station_ip"]), int(self.cfg["udp_port"]))
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setblocking(False)
            self.detection_pub = self.create_publisher(String, "/vision/detections", 1)
            self.cue_pub = self.create_publisher(String, "/vision/target_cue", 1)
            self.model = None
            self.model_id = None
            self.model_mode = None
            self.class_map = None
            self._load_model()
            path = str(self.cfg["vision_socket"])
            if '"' in path or not path.startswith("/"):
                raise ValueError("vision socket must be an absolute path without quotes")
            self.pipeline = Gst.parse_launch(
                f'shmsrc socket-path="{path}" is-live=true do-timestamp=true '
                f'! video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1 '
                '! queue max-size-buffers=1 leaky=downstream '
                '! appsink name=vision_sink sync=false max-buffers=1 drop=true'
            )
            self.sink = self.pipeline.get_by_name("vision_sink")
            if not isinstance(self.sink, GstApp.AppSink):
                raise RuntimeError("GStreamer appsink unavailable")
            self.bus = self.pipeline.get_bus()
            self.pipeline.set_state(Gst.State.PLAYING)
            self.sequence = 0
            self.last_status_ns = 0

        def _load_model(self):
            path_string = str(self.cfg["model_path"])
            expected = str(self.cfg["model_sha256"]).lower()
            if not path_string:
                self.get_logger().warning("model path absent; detection disabled")
                return
            path = Path(path_string)
            try:
                actual = model_sha256(path)
                if expected and actual != expected:
                    raise ValueError("model SHA-256 differs from vision.yaml")
                import torch
                torch.set_num_threads(int(self.cfg["cpu_threads"]))
                from ultralytics import YOLO
                model = YOLO(str(path), task="detect")
                self.class_map, self.model_mode = class_mapping(model.names)
            except Exception as error:
                # A broken backend must not produce a target cue. Video is separate.
                self.get_logger().error(f"vision model unavailable: {error}")
                return
            self.model = model
            self.model_id = actual[:16]

        def _image(self, sample):
            info = GstVideo.VideoInfo()
            if not info.from_caps(sample.get_caps()) or str(info.finfo.name) != "BGR":
                raise ValueError("shared camera frame is not BGR")
            buffer = sample.get_buffer()
            ok, mapped = buffer.map(Gst.MapFlags.READ)
            if not ok:
                raise RuntimeError("cannot map shared frame")
            try:
                # A row may be padded; honor the GStreamer stride before copying.
                image = np.ndarray((info.height, info.width, 3), dtype=np.uint8,
                                   buffer=mapped.data, strides=(info.stride[0], 3, 1)).copy()
            finally:
                buffer.unmap(mapped)
            return np.rot90(image, 1).copy(), int(buffer.pts)

        def _publish(self, payload):
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            message = String(data=encoded)
            self.detection_pub.publish(message)
            cue = {key: payload.get(key) for key in
                   ("schema", "sequence", "state", "direction", "processing_ms", "model_id", "model_mode")}
            self.cue_pub.publish(String(data=json.dumps(cue, separators=(",", ":"))))
            try:
                self.udp.sendto(encoded.encode("utf-8"), self.destination)
            except (BlockingIOError, OSError) as error:
                self.get_logger().warning(f"GCS cue send failed: {error}")
            self.last_status_ns = time.monotonic_ns()

        def _status(self, state):
            if time.monotonic_ns() - self.last_status_ns < 1_000_000_000:
                return
            self._publish({
                "schema": 1, "sequence": self.sequence, "state": state,
                "direction": None, "detections": [], "width": None, "height": None,
                "model_id": self.model_id, "model_mode": self.model_mode,
                "processing_ms": None,
                "timestamp_source": "HOST_RECEIVE", "receive_time_unix_ns": None,
            })

        def run(self):
            while rclpy.ok():
                rclpy.spin_once(self, timeout_sec=0.0)
                event = self.bus.timed_pop_filtered(
                    0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
                if event is not None:
                    raise RuntimeError(f"shared camera input ended: {event.type}")
                sample = self.sink.try_pull_sample(100 * Gst.MSECOND)
                if sample is None:
                    self._status("MODEL_UNAVAILABLE" if self.model is None else "STALE")
                    continue
                while True:
                    newer = self.sink.try_pull_sample(0)
                    if newer is None:
                        break
                    sample = newer
                if self.model is None:
                    self._status("MODEL_UNAVAILABLE")
                    continue
                frame, pts = self._image(sample)
                received_ns = time.monotonic_ns()
                received_unix_ns = time.time_ns()
                result = self.model.predict(
                    frame, imgsz=(int(self.cfg["input_height"]), int(self.cfg["input_width"])),
                    conf=float(self.cfg["confidence"]), device="cpu", verbose=False,
                )[0]
                height, width = frame.shape[:2]
                detections = []
                for box in result.boxes:
                    if len(detections) == 12:
                        break  # Keep the UDP payload bounded.
                    detections.append(make_detection(
                        int(box.cls[0]), float(box.conf[0]),
                        box.xyxy[0].cpu().tolist(), width, height, self.class_map))
                processing_ms = (time.monotonic_ns() - received_ns) / 1_000_000
                state, direction = cue_from_detections(detections, width)
                if processing_ms > float(self.cfg["max_result_age_ms"]):
                    state, direction, detections = "STALE", None, []
                self.sequence += 1
                self._publish({
                    "schema": 1, "sequence": self.sequence, "state": state,
                    "direction": direction, "detections": detections,
                    "width": width, "height": height, "model_id": self.model_id,
                    "model_mode": self.model_mode,
                    "processing_ms": round(processing_ms, 2),
                    "timestamp_source": "HOST_RECEIVE",
                    "receive_time_unix_ns": received_unix_ns, "gst_pts_ns": pts,
                })

        def close(self):
            self.pipeline.set_state(Gst.State.NULL)
            self.udp.close()

    rclpy.init()
    node = None
    try:
        node = VisionNode()
        node.run()
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
