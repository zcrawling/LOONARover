import struct
import unittest
from backend.protocol import MAGIC, MAX_BODY, Parser, ProtocolError, encode
from backend.config import load


class ProtocolTests(unittest.TestCase):
    def test_fragmentation_and_multiple_frames(self):
        one = {"kind": "command", "command": "MANUAL", "request_id": "abc"}
        two = {"kind": "pong", "sequence": 1}
        wire = encode(one) + encode(two)
        p = Parser()
        out = []
        for byte in wire:
            out.extend(p.feed(bytes([byte])))
        self.assertEqual(out, [one, two])
        self.assertEqual(Parser().feed(wire), [one, two])

    def test_invalid_header_lengths_and_data(self):
        for data in (struct.pack("!4sI", b"LNK1", 10),
                     struct.pack("!4sI", MAGIC, MAX_BODY+1),
                     struct.pack("!4sI", MAGIC, 0),
                     struct.pack("!4sI", MAGIC, 2)+b"xx"):
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                Parser().feed(data)

    def test_schema_and_nonfinite_values(self):
        for obj in ({"kind": "bad"}, {"kind": "command", "command": "STOP"},
                    {"kind": "pong", "sequence": True},
                    {"kind": "ping", "sequence": 1, "value": float('nan')}):
            with self.subTest(obj=obj), self.assertRaises(ProtocolError):
                encode(obj)

    def test_default_config(self):
        c = load()
        self.assertEqual(c['command']['payload_receipt_timeout'], 20)
        self.assertEqual(c['network']['target'], 'mock')


if __name__ == '__main__':
    unittest.main()
