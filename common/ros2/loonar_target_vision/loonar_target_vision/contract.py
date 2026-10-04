"""Pure data contract shared by the detector's ROS and UDP outputs."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

CLASSES = ("target_rover", "obstacle")


def model_sha256(path: Path) -> str:
    """Hash a model file or an exported model directory in stable path order."""
    digest = hashlib.sha256()
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    if not files:
        raise FileNotFoundError(path)
    for file in files:
        digest.update((file.relative_to(path) if path.is_dir() else file.name).as_posix().encode())
        digest.update(b"\0")
        with file.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def class_mapping(names: dict | list) -> tuple[dict[int, int], str]:
    """Accept the temporary COCO demo or the later two-class mission model."""
    actual = dict(enumerate(names)) if isinstance(names, (list, tuple)) else {
        int(key): value for key, value in names.items()}
    if not actual or any(i < 0 or not isinstance(name, str) for i, name in actual.items()):
        raise ValueError("invalid model classes")
    if [actual.get(i) for i in range(len(actual))] == list(CLASSES):
        return {0: 0, 1: 1}, "MISSION"
    return {i: (0 if name.strip().lower() in {"rover", "target_rover"} else 1)
            for i, name in actual.items()}, "DEMO"


def make_detection(class_id: int, confidence: float, xyxy, width: int, height: int,
                   mapping: dict[int, int] | None = None) -> dict:
    if mapping is not None:
        class_id = mapping[class_id]
    if class_id not in (0, 1) or not math.isfinite(confidence):
        raise ValueError("invalid class or confidence")
    x0, y0, x1, y1 = [float(v) for v in xyxy]
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        raise ValueError("nonfinite detection box")
    box = [max(0.0, min(float(limit), value)) for value, limit in
           zip((x0, y0, x1, y1), (width, height, width, height))]
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError("empty detection box")
    return {"class_id": class_id, "class_name": CLASSES[class_id],
            "confidence": confidence, "xyxy": box}


def direction_for_box(box, width: int) -> str:
    center = (box[0] + box[2]) / 2
    if center < width / 3:
        return "LEFT"
    if center >= 2 * width / 3:
        return "RIGHT"
    return "CENTER"


def cue_from_detections(detections: list[dict], width: int) -> tuple[str, str | None]:
    targets = [d for d in detections if d["class_id"] == 0]
    if not targets:
        return "NOT_DETECTED", None
    best = max(targets, key=lambda d: d["confidence"])
    return "DETECTED", direction_for_box(best["xyxy"], width)
