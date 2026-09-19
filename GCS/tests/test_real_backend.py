import struct
import unittest

from backend.real_app import GroundLinkConnection, RealState, HEADER


class Writer:
    def __init__(self): self.data = []
    def write(self, data): self.data.append(data)
    async def drain(self): pass


class RealBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_auto_and_safe_manual_frames(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        for command, expected_type, expected_payload in (
            ("STOP", 0x0001, b""),
            ("MANUAL", 0x0002, struct.pack("<dd", 0.0, 0.0)),
            ("AUTO", 0x0003, b""),
        ):
            result = await connection.command(command)
            self.assertTrue(result["ok"])
            magic, version, frame_type, sequence, length = HEADER.unpack_from(writer.data[-1])
            self.assertEqual((magic, version, frame_type), (b"LNK1", 1, expected_type))
            self.assertGreater(sequence, 0)
            self.assertEqual(writer.data[-1][HEADER.size:], expected_payload)
            self.assertEqual(length, len(expected_payload))

    async def test_undefined_activity_commands_are_not_sent(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        for command in ("PAYLOAD", "REACTION"):
            result = await connection.command(command)
            self.assertFalse(result["ok"])
        self.assertEqual(writer.data, [])

    async def test_web_keyboard_motion_frames(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state,
            manual_control={"linear_speed_mps": 0.1, "angular_speed_radps": 0.5})
        writer = Writer()
        connection.writer = writer
        expected = {
            "FORWARD": (0.1, 0.0), "LEFT": (0.0, 0.5),
            "REVERSE": (-0.1, 0.0), "RIGHT": (0.0, -0.5),
        }
        for command, values in expected.items():
            self.assertTrue((await connection.command(command))["ok"])
            header = HEADER.unpack_from(writer.data[-1])
            self.assertEqual(header[2], 0x0002)
            self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), values)

    async def test_adjustable_linear_speed(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        self.assertTrue((await connection.command("FORWARD", 0.37))["ok"])
        self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), (0.37, 0.0))
        self.assertFalse((await connection.command("FORWARD", 1.01))["ok"])

    def test_real_telemetry_updates_web_snapshot(self):
        state = RealState("192.0.2.10")
        connection = GroundLinkConnection("192.0.2.10", 7443, state)
        connection.handle(0x8002, struct.pack("<BBBBdd", 3, 3, 1, 0, 0.0, 0.0))
        connection.handle(0x8003, struct.pack("<QI10d", 123, 0x1D, 12.4, 0.0,
                          1.0, 2.0, 0.3, 0.1, 0.2, 0.01, 0.02, 0.03))
        snapshot = state.snapshot()
        self.assertEqual(snapshot["source"], "REAL ROVER / 192.0.2.10")
        self.assertEqual(snapshot["status"]["mode"], "STOP")
        self.assertEqual(snapshot["status"]["values"]["배터리 전압 (V)"], 12.4)
        self.assertIsNone(snapshot["status"]["values"]["배터리 잔량 (%)"])


if __name__ == "__main__": unittest.main()
