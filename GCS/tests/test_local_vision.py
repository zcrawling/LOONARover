"""Latest-frame inference lifecycle without camera, ROS or model dependencies."""
import sys
from pathlib import Path
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cli.local_vision import LocalVision
from cli.vision_overlay import VisionCache


def result():
    return dict(state="NOT_DETECTED", direction=None, detections=[],
                width=360, height=640, model_mode="DEMO")


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("worker did not reach expected state")


class LocalVisionTests(unittest.TestCase):
    def test_off_skips_loading_and_resume_keeps_one_model(self):
        loaded, seen = [], []
        def loader():
            loaded.append(True)
            return lambda frame: (seen.append(frame) or result())
        cache = VisionCache()
        worker = LocalVision(cache, loader, enabled=False)
        worker.start()
        try:
            worker.submit('disabled')
            time.sleep(.03)
            self.assertEqual(loaded, [])
            self.assertIsNone(worker.pending)
            self.assertIn('OBJ OFF', worker.status)
            worker.set_enabled(True)
            worker.submit('first')
            wait_for(lambda: cache.sequence == 0)
            worker.set_enabled(False)
            self.assertIsNone(cache.snapshot())
            worker.submit('disabled again')
            time.sleep(.15)
            self.assertEqual(seen, ['first'])
            worker.set_enabled(True)
            worker.submit('second')
            wait_for(lambda: cache.sequence == 1)
            self.assertEqual(seen, ['first', 'second'])
            self.assertEqual(len(loaded), 1)
        finally:
            worker.close()

    def test_off_on_discards_inflight_result_and_pending_frame(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        seen = []
        def detect(frame):
            seen.append(frame)
            if frame == 'old':
                entered.set()
                release.wait(2)
                finished.set()
            return result()
        cache = VisionCache()
        worker = LocalVision(cache, lambda: detect)
        worker.start()
        try:
            worker.submit('old')
            self.assertTrue(entered.wait(2))
            worker.submit('queued')
            worker.set_enabled(False)
            worker.set_enabled(True)
            release.set()
            self.assertTrue(finished.wait(2))
            time.sleep(.05)
            self.assertIsNone(cache.snapshot())
            self.assertEqual(seen, ['old'])
            worker.submit('new')
            wait_for(lambda: cache.snapshot() is not None)
            self.assertEqual(seen, ['old', 'new'])
        finally:
            release.set()
            worker.close()

    def test_inference_does_not_block_submit_and_only_newest_frame_survives(self):
        entered, release = threading.Event(), threading.Event()
        seen = []
        def detect(frame):
            seen.append(frame)
            if frame == 1:
                entered.set()
                release.wait(2)
            return result()
        cache = VisionCache()
        worker = LocalVision(cache, lambda: detect)
        worker.start()
        try:
            worker.submit(1)
            self.assertTrue(entered.wait(2))
            # This would deadlock if submit waited for inference.
            for frame in range(2, 101):
                worker.submit(frame)
            release.set()
            wait_for(lambda: cache.sequence == 1)
            self.assertEqual(seen, [1, 100])
            self.assertIsNotNone(cache.snapshot())
        finally:
            release.set()
            worker.close()
        self.assertFalse(worker.thread.is_alive())

    def test_loading_discards_old_frames(self):
        loaded, release = threading.Event(), threading.Event()
        seen = []
        def loader():
            loaded.set()
            release.wait(2)
            return lambda frame: (seen.append(frame) or result())
        cache = VisionCache()
        worker = LocalVision(cache, loader)
        worker.start()
        try:
            self.assertTrue(loaded.wait(2))
            worker.submit("old", time.monotonic() - 2)
            release.set()
            wait_for(lambda: worker.pending is None)
            self.assertEqual(seen, [])
            worker.submit("new", flipped=True)
            wait_for(lambda: cache.sequence == 0)
            self.assertEqual(seen, ["new"])
            self.assertTrue(cache.snapshot()[0]['flipped'])
        finally:
            release.set()
            worker.close()

    def test_slow_result_does_not_draw_old_boxes(self):
        cache = VisionCache()
        def slow(frame):
            time.sleep(.51)
            return result()
        worker = LocalVision(cache, lambda: slow)
        worker.start()
        try:
            worker.submit(1)
            wait_for(lambda: cache.sequence == 0)
            packet, _ = cache.snapshot()
            self.assertEqual(packet["state"], "STALE")
            self.assertEqual(packet["detections"], [])
        finally:
            worker.close()

    def test_model_failure_keeps_caller_operational(self):
        def fail():
            raise RuntimeError("test missing model")
        worker = LocalVision(VisionCache(), fail)
        worker.start()
        worker.thread.join(2)
        self.assertIn("사용 불가", worker.status)
        worker.submit(1)
        worker.close()


if __name__ == "__main__":
    unittest.main()
