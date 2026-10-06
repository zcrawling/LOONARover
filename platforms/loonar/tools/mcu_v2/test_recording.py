import importlib.util
from pathlib import Path
import struct
import unittest

from .motor_sample import decode_motor
from .recording_monitor import StreamState

CAMERA = Path(__file__).resolve().parents[4] / "common/video/camera_ros.py"
spec = importlib.util.spec_from_file_location("camera_ros", CAMERA)
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


class RecordingTests(unittest.TestCase):
    def test_motor_offsets_units_and_validity(self):
        raw = bytearray(64)
        struct.pack_into("<I6i", raw, 0, 255, -123, 456, -1000, 2000, -1100, 2100)
        struct.pack_into("<4h3H", raw, 28, -125, 250, -32767, 16384, 241, 51, 365)
        raw[42] = 1
        struct.pack_into("<5I", raw, 44, 0x10000, 12, 3, 4, 5)
        d = decode_motor(raw)
        self.assertEqual((d["left_count"], d["right_speed_qpps"]), (-123, 2000))
        self.assertEqual((d["left_current_a"], d["right_current_a"]), (-1.25, 2.5))
        self.assertEqual((d["main_voltage_v"], d["logic_voltage_v"], d["temperature_c"]), (24.1, 5.1, 36.5))
        self.assertEqual((d["left_pwm_raw"], d["speed_age_ms"], d["error"]), (-32767, 5, 0x10000))
        self.assertTrue(d["pwm_valid"])
        raw[0] = 2
        d = decode_motor(raw)
        self.assertFalse(d["current_valid"])
        self.assertTrue(d["speed_valid"])
        with self.assertRaises(ValueError):
            decode_motor(raw[:-1])

    def test_clock_mapping_preserves_pipeline_age(self):
        wall = 1_790_000_000_000_000_000
        self.assertEqual(camera.frame_stamp(wall, 10_100_000_000, 10_000_000_000, 60_000_000),
                         (wall - 40_000_000, 40_000_000))
        for pts in (-1, 200_000_000):
            self.assertEqual(camera.frame_stamp(wall, 10_100_000_000, 10_000_000_000, pts), (wall, None))

    def test_missing_stale_future_and_invalid_samples(self):
        state = StreamState(["motor", "imu"])
        now = 10_000_000_000
        self.assertFalse(state.snapshot(now)["imu"]["fresh"])
        state.update("motor", now - 100_000_000, True)
        self.assertTrue(state.snapshot(now)["motor"]["fresh"])
        self.assertFalse(state.snapshot(now + 3_000_000_000)["motor"]["fresh"])
        state.update("motor", now + 100_000_000, True)
        self.assertFalse(state.snapshot(now)["motor"]["fresh"])
        state.update("motor", now, False)
        self.assertFalse(state.snapshot(now)["motor"]["fresh"])
        self.assertEqual(state.snapshot(now)["motor"]["count"], 3)
