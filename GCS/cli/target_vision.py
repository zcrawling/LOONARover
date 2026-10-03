"""Ground-station RGB detection contract for the portrait camera preview."""

from dataclasses import dataclass
from pathlib import Path
import time


CLASSES = {0: 'target_rover', 1: 'obstacle'}
MAX_RESULT_AGE_S = 0.5
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / 'models' / 'mission02' / 'yolo26n.pt'


@dataclass(frozen=True)
class Box:
    name: str
    confidence: float
    xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class Result:
    frame_time: float  # GCS receive/decode time, not camera exposure time
    size: tuple[int, int]
    boxes: tuple[Box, ...]
    direction: str
    inference_ms: float


def check_classes(names):
    """Map a detection model's rover class to 0 and every other class to 1."""
    actual = dict(enumerate(names)) if isinstance(names, (list, tuple)) else {
        int(key): value for key, value in names.items()}
    if not actual or any(index < 0 or not isinstance(name, str) for index, name in actual.items()):
        raise ValueError(f'Invalid model classes: {actual}')
    return {index: ('target_rover' if name.strip().lower() in {'rover', 'target_rover'}
                    else 'obstacle') for index, name in actual.items()}


def direction_for_boxes(boxes, width):
    targets = [box for box in boxes if box.name == 'target_rover']
    if not targets:
        return 'NOT_DETECTED'
    target = max(targets, key=lambda box: box.confidence)
    center = (target.xyxy[0] + target.xyxy[2]) / 2
    return 'LEFT' if center < width / 3 else 'RIGHT' if center >= 2 * width / 3 else 'CENTER'


def result_is_fresh(result, now=None):
    now = time.monotonic() if now is None else now
    return result is not None and 0 <= now - result.frame_time <= MAX_RESULT_AGE_S


def extract_result(prediction, size, frame_time, inference_ms, class_map=None):
    """Convert Ultralytics boxes to portrait-frame pixel coordinates."""
    class_map = CLASSES if class_map is None else class_map
    width, height = size
    boxes = []
    for item in prediction.boxes:
        class_id = int(item.cls.item())
        if class_id not in class_map:
            raise ValueError(f'Unexpected class ID: {class_id}')
        x1, y1, x2, y2 = (float(v) for v in item.xyxy[0].tolist())
        x1, x2 = sorted((max(0, min(width, x1)), max(0, min(width, x2))))
        y1, y2 = sorted((max(0, min(height, y1)), max(0, min(height, y2))))
        boxes.append(Box(class_map[class_id], float(item.conf.item()), (x1, y1, x2, y2)))
    boxes = tuple(boxes)
    return Result(frame_time, size, boxes, direction_for_boxes(boxes, width), inference_ms)
