"""CPU detection on the latest decoded GCS frame, independent of display."""
import json
from pathlib import Path
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = REPO / "GCS/models/mission02/best.pt"
sys.path.insert(0, str(REPO / "common/ros2/loonar_target_vision"))
from loonar_target_vision.contract import class_mapping, cue_from_detections, make_detection


class Detector:
    def __init__(self, model_path=DEFAULT_MODEL):
        # Never download a missing model while the operator is waiting for video.
        if not Path(model_path).is_file():
            raise FileNotFoundError(model_path)
        import torch
        import numpy as np
        from ultralytics import YOLO
        torch.set_num_threads(2)
        self.model = YOLO(str(model_path), task="detect")
        self.mapping, self.mode = class_mapping(self.model.names)
        # Ultralytics changes Torch's thread count during first predictor setup.
        # Warm up off the display thread, then restore our CPU budget.
        self.predict(np.zeros((640, 360, 3), dtype=np.uint8))
        torch.set_num_threads(2)

    def predict(self, bgr):
        return self.model.predict(bgr, device="cpu", imgsz=(640, 384),
                                  conf=0.35, rect=False, verbose=False,
                                  save=False, max_det=12)[0]

    def __call__(self, frame):
        import numpy as np
        # The viewer already applied rotation; use those same coordinates.
        bgr = np.asarray(frame)[:, :, ::-1].copy()
        result = self.predict(bgr)
        detections = [
            make_detection(int(cls), float(conf), box, frame.width, frame.height, self.mapping)
            for cls, conf, box in zip(result.boxes.cls.tolist(),
                                      result.boxes.conf.tolist(), result.boxes.xyxy.tolist())]
        state, direction = cue_from_detections(detections, frame.width)
        return dict(state=state, direction=direction, detections=detections,
                    width=frame.width, height=frame.height, model_mode=self.mode)


class LocalVision:
    """One in-flight inference plus one replaceable frame; no growing queue."""
    def __init__(self, cache, loader=Detector, *, enabled=True):
        self.cache = cache
        self.loader = loader
        self.condition = threading.Condition()
        self.pending = None
        self.stopped = False
        self.enabled = enabled
        self.generation = 0
        self._status = "PC 인식 모델 로딩 중"
        self.thread = threading.Thread(target=self.run, name="gcs-vision", daemon=True)

    def start(self):
        self.thread.start()

    @property
    def status(self):
        return self._status if self.enabled else 'OBJ OFF · 객체인식 중지'

    def set_enabled(self, enabled):
        with self.condition:
            if self.enabled != enabled:
                self.enabled = enabled
                self.generation += 1
                self.pending = None
                self.cache.clear()
                self.condition.notify()

    def submit(self, frame, received=None, *, flipped=False):
        with self.condition:
            if not self.stopped and self.enabled:
                self.pending = (frame, time.monotonic() if received is None else received, flipped)
                self.condition.notify()

    def close(self):
        with self.condition:
            self.stopped = True
            self.pending = None
            self.condition.notify()
        self.thread.join(timeout=1)

    def run(self):
        sequence = 0
        try:
            with self.condition:
                while not self.stopped and not self.enabled:
                    self.condition.wait()
                if self.stopped:
                    return
            detect = self.loader()
            self._status = "OBJ ON · PC 인식 영상 대기/갱신 지연"
            next_frame = 0.0
            while True:
                with self.condition:
                    while not self.stopped:
                        delay = max(0.0, next_frame - time.monotonic())
                        if self.enabled and self.pending is not None and delay == 0:
                            break
                        self.condition.wait(timeout=delay if self.enabled and delay else None)
                    if self.stopped:
                        return
                    frame, received, flipped = self.pending
                    generation = self.generation
                    self.pending = None
                if time.monotonic() - received > 0.5:
                    continue
                started = time.monotonic()
                packet = detect(frame)
                age_ms = (time.monotonic() - received) * 1000
                packet.update(schema=1, sequence=sequence, processing_ms=age_ms, flipped=flipped)
                if age_ms > 500:
                    packet.update(state="STALE", direction=None, detections=[])
                with self.condition:
                    if self.stopped:
                        return
                    if not self.enabled or generation != self.generation:
                        continue
                    self.cache.update(json.dumps(packet).encode())
                sequence += 1
                next_frame = started + 0.1  # At most 10 Hz; display runs independently.
        except Exception as error:
            self._status = "PC 인식 사용 불가 (영상 터미널 오류 확인)"
            print(f"GCS object detection unavailable: {error}", file=sys.stderr)
