import struct
import unittest

from cli.groundlink_monitor import FrameParser, HEADER, ProtocolError, decode_payload


def frame(frame_type, payload, sequence=0):
    return HEADER.pack(b"LNK1", 1, frame_type, sequence, len(payload)) + payload


class GroundLinkMonitorTests(unittest.TestCase):
    def test_fragmented_and_multiple_frames(self):
        gateway = struct.pack("<BBBBdd", 3, 3, 1, 0, 0.0, 0.0)
        command = struct.pack("<IHBBBB", 7, 1, 1, 1, 3, 0)
        wire = frame(0x8002, gateway) + frame(0x8001, command, 7)
        parser = FrameParser()
        self.assertEqual(parser.feed(wire[:10]), [])
        messages = parser.feed(wire[10:])
        self.assertEqual([item[0] for item in messages], [0x8002, 0x8001])
        self.assertEqual(decode_payload(*messages[0][::2])["mode"], "STOP")

    def test_vehicle_valid_flags_hide_unavailable_values(self):
        payload = struct.pack("<QI10d", 123, 0b00101, 11.7, 99.0, 1.0, 2.0, 3.0,
                              0.4, 0.5, 0.1, 0.2, 0.3)
        decoded = decode_payload(0x8003, payload)
        self.assertEqual(decoded["battery_voltage"], 11.7)
        self.assertIsNone(decoded["battery_percent"])
        self.assertEqual(decoded["odom_x"], 1.0)
        self.assertIsNone(decoded["linear_mps"])

    def test_rejects_bad_header_and_payload_size(self):
        parser = FrameParser()
        with self.assertRaises(ProtocolError):
            parser.feed(HEADER.pack(b"BAD!", 1, 0x8002, 0, 0))
        with self.assertRaises(ProtocolError):
            decode_payload(0x8002, b"short")


if __name__ == "__main__":
    unittest.main()
