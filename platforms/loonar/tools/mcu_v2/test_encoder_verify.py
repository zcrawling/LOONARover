import tempfile
import unittest
from pathlib import Path
import struct
from .encoder_verify import EncoderVerify


class EncoderVerifyTests(unittest.TestCase):
    def test_valid_straight_only_and_signed_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EncoderVerify(Path(directory) / 'test.csv')
            def feed(t, command=100, right_command=None, age=0, valid=3, boot=1):
                p = bytearray(64)
                struct.pack_into('<I6i', p, 0, valid, 10, 12, 90, 100, command,
                                 command if right_command is None else right_command)
                p[42] = 1
                struct.pack_into('<5I', p, 44, 0, 0, 0, age, age)
                return logger.feed(dict(payload=p.hex(), stamp_ns=t, boot=boot, seq=t), t)
            try:
                for i in range(12):
                    state = feed(1_000_000_000 + i * 100_000_000)
                self.assertEqual(state, 'STRAIGHT')
                self.assertEqual(logger.n, 2)
                self.assertEqual(logger.worst, 10)
                self.assertEqual(feed(2_200_000_000, age=300), 'STALE/FAULT')
                self.assertEqual(feed(2_300_000_000, command=0), 'STOP/TURN')
                self.assertEqual(feed(2_400_000_000, right_command=50), 'STOP/TURN')
                self.assertEqual(feed(2_500_000_000, command=-100), 'SETTLING')
                for i in range(1, 12):
                    state = feed(2_500_000_000+i*100_000_000, command=-100)
                self.assertEqual(state, 'STRAIGHT')
                self.assertEqual(feed(3_700_000_000, command=-100, boot=2), 'SETTLING')
                self.assertEqual(feed(3_800_000_000, valid=1), 'STALE/FAULT')
            finally:
                logger.close()
