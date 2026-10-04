"""Validate and map recent RGB detections without delaying the video player."""

from __future__ import annotations

import json
import math
import socket
import threading
import time

VALID_STATES = {"DETECTED", "NOT_DETECTED", "STALE", "MODEL_UNAVAILABLE"}
VALID_DIRECTIONS = {"LEFT", "CENTER", "RIGHT"}


def parse_packet(raw: bytes) -> dict:
    if len(raw) > 4096:
        raise ValueError("vision packet too large")
    packet = json.loads(raw.decode("utf-8"))
    if not isinstance(packet, dict) or type(packet.get("schema")) is not int or packet["schema"] != 1:
        raise ValueError("unknown vision packet schema")
    state = packet.get("state")
    if state not in VALID_STATES:
        raise ValueError("invalid vision state")
    if packet.get("model_mode") not in (None, "DEMO", "MISSION"):
        raise ValueError("invalid vision model mode")
    if state == "DETECTED" and packet.get("direction") not in VALID_DIRECTIONS:
        raise ValueError("detected target needs direction")
    if state != "DETECTED" and packet.get("direction") is not None:
        raise ValueError("unexpected target direction")
    age = packet.get("processing_ms")
    if age is not None and (not isinstance(age, (int, float)) or
                            not math.isfinite(age) or age < 0):
        raise ValueError("invalid processing age")
    if state in ("DETECTED", "NOT_DETECTED"):
        width, height = packet.get("width"), packet.get("height")
        if not all(isinstance(v, int) and 0 < v <= 4096 for v in (width, height)):
            raise ValueError("invalid source dimensions")
        detections = packet.get("detections")
        if not isinstance(detections, list) or len(detections) > 12:
            raise ValueError("invalid detections")
        for item in detections:
            if (not isinstance(item, dict) or type(item.get("class_id")) is not int or
                    item["class_id"] not in (0, 1) or
                    item.get("class_name") != ("target_rover", "obstacle")[item["class_id"]]):
                raise ValueError("invalid detection class")
            box = item.get("xyxy")
            score = item.get("confidence")
            if (not isinstance(box, list) or len(box) != 4 or
                    not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box) or
                    not isinstance(score, (int, float)) or not math.isfinite(score) or
                    not 0 <= score <= 1 or
                    not (0 <= box[0] < box[2] <= width and
                         0 <= box[1] < box[3] <= height)):
                raise ValueError("invalid detection geometry")
    return packet


def canvas_box(box, source_width, source_height, video_rectangle):
    """Map an already-rotated source box into the displayed portrait image."""
    x, y, x1, y1 = video_rectangle
    sx = (x1 - x) / source_width
    sy = (y1 - y) / source_height
    return (x + box[0] * sx, y + box[1] * sy,
            x + box[2] * sx, y + box[3] * sy)


class VisionCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.packet = None
        self.arrival = 0.0
        self.sequence = -1

    def update(self, raw: bytes, now=None):
        packet = parse_packet(raw)
        sequence = packet.get("sequence")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("invalid vision sequence")
        with self.lock:
            # A restarted detector can begin at zero; status then recovers on timeout.
            if self.packet is not None and sequence < self.sequence and time.monotonic() - self.arrival < 1.5:
                return
            self.packet, self.sequence = packet, sequence
            self.arrival = time.monotonic() if now is None else now

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.packet is None:
                return None
            packet = self.packet
            total_age = (packet.get("processing_ms") or 0) + (now - self.arrival) * 1000
            ttl = 500 if packet["state"] in ("DETECTED", "NOT_DETECTED") else 1500
            if total_age < 0 or total_age > ttl:
                return None
            return packet, total_age


def receive_packets(cache: VisionCache, stop: threading.Event, port: int, allowed_ip=""):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("0.0.0.0", port))
        server.settimeout(0.25)
        while not stop.is_set():
            try:
                raw, address = server.recvfrom(4097)
                if allowed_ip and address[0] != allowed_ip:
                    continue
                cache.update(raw)
            except socket.timeout:
                continue
            except (UnicodeError, ValueError):
                continue
