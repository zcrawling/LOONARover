import struct
import unittest

from backend.config import load_manual_control
from cli.keyboard_control import HEADER, command_for_key, with_sequence


class KeyboardControlTests(unittest.TestCase):
    def setUp(self):
        self.config = load_manual_control()

    def values(self, key):
        _, frame = command_for_key(key, self.config)
        magic, version, frame_type, sequence, length = HEADER.unpack_from(frame)
        return magic, version, frame_type, sequence, length, frame[HEADER.size:]

    def test_direction_values(self):
        expected = {
            "PAGE_UP": (0.1, 0.0),
            "HOME": (0.0, 0.5),
            "PAGE_DOWN": (-0.1, 0.0),
            "END": (0.0, -0.5),
        }
        for key, values in expected.items():
            with self.subTest(key=key):
                magic, version, frame_type, sequence, length, payload = self.values(key)
                self.assertEqual((magic, version, frame_type, sequence, length),
                                 (b"LNK1", 1, 0x0002, 0, 16))
                self.assertEqual(struct.unpack("<dd", payload), values)

    def test_stop_and_sequence(self):
        _, frame = command_for_key("SPACE", self.config)
        numbered = with_sequence(frame, 42)
        self.assertEqual(HEADER.unpack(numbered), (b"LNK1", 1, 0x0001, 42, 0))


if __name__ == "__main__":
    unittest.main()
