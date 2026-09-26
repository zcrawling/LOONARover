"""LOONAR wire compatibility, without network connections or physical devices."""
import struct
import unittest
from pathlib import Path

from backend.config import load_manual_control
from backend.real_app import GroundLinkConnection, RealState
from cli.groundlink_monitor import HEADER, FrameParser, ProtocolError, decode_payload


def health(role=1, online=1):
    raw = bytearray(128)
    struct.pack_into("<4sBBHIIQQII", raw, 0, b"MCU2", role, online, 2,
                     10, 20, 123456, 0x123456789ABC, 25, 3)
    struct.pack_into("<Qf", raw, 48, 1234, 42.5)
    struct.pack_into("<14I", raw, 60, 8, 99, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    raw[116:118] = bytes((1, 1))
    struct.pack_into("<I", raw, 120, 13)
    return bytes(raw)


class LoonarMcuTests(unittest.TestCase):
    def test_battery_voltage_without_percentage_or_wheel_feedback(self):
        state = RealState("pi")
        connection = GroundLinkConnection("pi", 7443, state)
        connection.handle(0x8003, struct.pack("<QI10d", 123, 1, 16.7, *([0.0] * 9)))
        values = state.snapshot()["status"]["values"]
        self.assertAlmostEqual(values["배터리 전압 (V)"], 16.7)
        self.assertIsNone(values["배터리 잔량 (%)"])
        self.assertIsNone(values["선속도 (m/s)"])
        connection.handle(0x8003, struct.pack("<QI10d", 124, 0, *([0.0] * 10)))
        self.assertIsNone(state.snapshot()["status"]["values"]["배터리 전압 (V)"])

    def test_loonar_launcher_uses_confirmed_initial_speed(self):
        config = load_manual_control(Path(__file__).resolve().parents[1] / "config/loonar.toml")
        self.assertEqual(config["linear_speed_mps"], 0.03)
        self.assertEqual(config["repeat_interval_ms"], 50)

    def test_fragmented_mcu_and_gateway_frames_remain_on_same_connection(self):
        raw = health()
        gateway = struct.pack("<BBBBdd", 2, 2, 1, 0, 0.03, 0)
        wire = HEADER.pack(b"LNK1", 1, 0x8007, 0, 128) + raw
        wire += HEADER.pack(b"LNK1", 1, 0x8002, 0, 20) + gateway
        parser = FrameParser()
        frames = []
        for at in range(0, len(wire), 7):
            frames.extend(parser.feed(wire[at:at+7]))
        self.assertEqual([f[0] for f in frames], [0x8007, 0x8002])
        data = decode_payload(frames[0][0], frames[0][2])
        self.assertEqual(data["uid"], "0000123456789abc")
        self.assertEqual(data["temperature_c"], 42.5)
        self.assertEqual(data["inhibit"], 8)
        self.assertEqual(data["driver_ack_age_ms"], 9)
        self.assertEqual(data["driver_failures"], 13)
        self.assertTrue(data["identity_bound"])

    def test_control_and_offline_payload_are_kept_separate(self):
        state = RealState("pi")
        connection = GroundLinkConnection("pi", 7443, state)
        connection.handle(0x8007, health())
        connection.handle(0x8007, health(2, 0))
        snapshot = state.snapshot()
        self.assertTrue(snapshot["mcu"]["control"]["online"])
        self.assertFalse(snapshot["mcu"]["payload"]["online"])
        self.assertEqual(snapshot["status"]["values"]["Control MCU 온도 (°C)"], 42.5)
        self.assertIsNone(snapshot["status"]["values"]["Payload MCU 온도 (°C)"])
        self.assertNotIn("라즈베리파이 내부 온도 (°C)", snapshot["status"]["values"])

    def test_bad_health_headers_are_rejected(self):
        for raw in (health()[:-1], health(3), health(1, 2), b"BAD!" + health()[4:]):
            with self.assertRaises(ProtocolError):
                decode_payload(0x8007, raw)

    def test_cfs_forwarding_is_not_claimed_as_completed_motion(self):
        state = RealState("pi")
        state.pending["7"] = {"command": "FORWARD"}
        connection = GroundLinkConnection("pi", 7443, state)
        connection.handle(0x8001, struct.pack("<IHBBBB", 7, 2, 1, 1, 2, 0))
        self.assertEqual(state.pending["7"]["state"], "Forwarded")
        self.assertTrue(state.pending["7"]["adapter_forwarded"])


if __name__ == "__main__":
    unittest.main()
