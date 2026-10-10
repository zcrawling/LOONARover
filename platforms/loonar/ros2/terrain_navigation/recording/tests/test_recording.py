import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from loonar_recording.journal import emit, Reader, _handles
from loonar_recording.proxy import Frames
from mcu_v2.link import Link
from mcu_v2.test_v2 import FakeSerial
from mcu_v2.wire import Kind


class RecordingTests(unittest.TestCase):
    def tearDown(self):
        for stream, _ in _handles.values():
            stream.close()
        _handles.clear()

    def test_journal_partial_tail_and_binary_exactness(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LOONAR_CAPTURE_SESSION=tmp):
            emit('fixture', 'raw', bytes(range(256)))
            path=next((Path(tmp)/'raw').glob('*.journal'))
            reader=Reader(path)
            meta,data=reader.read()
            self.assertEqual(data,bytes(range(256)))
            self.assertEqual(meta['seq'],1)
            self.assertIsNone(reader.read())
            with path.open('ab') as file:
                file.write(b'\x03')
            self.assertIsNone(reader.read())
            self.assertEqual(reader.remaining,1)
            reader.close()

    def test_fragmented_manual_and_stop_frames(self):
        wire=struct.pack('<4sHHII2d',b'LNK1',1,2,8,16,.2,-.3)+struct.pack('<4sHHII',b'LNK1',1,1,9,0)
        parser=Frames(); frames=[]
        for byte in wire:
            frames.extend(parser.feed(bytes([byte])))
        self.assertEqual(frames,[(2,8,struct.pack('<2d',.2,-.3)),(1,9,b'')])
        with self.assertRaises(ValueError):
            Frames().feed(struct.pack('<4sHHII',b'LNK1',1,2,0,513))

    def test_serial_hook_records_actual_motion_and_close_stop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LOONAR_CAPTURE_SESSION=tmp):
            device={'device':'fake','role_id':1,'uid_int':1}
            link=Link(device,FakeSerial)
            payload=struct.pack('<IiiI',1,123,-456,200)
            link.send(Kind.MOTION,payload)
            link.close()
            reader=Reader(next((Path(tmp)/'raw').glob('*.journal')))
            rows=[]
            while (row:=reader.read()) is not None:
                rows.append(row)
            reader.close()
            tx=[m for m,d in rows if m['event']=='tx']
            self.assertEqual(tx[-2]['payload'],payload.hex())
            self.assertTrue(tx[-2]['complete'])
            self.assertEqual(tx[-1]['kind'],int(Kind.STOP))
            self.assertTrue(any(m['event']=='rx' for m,d in rows))


if __name__ == '__main__':
    unittest.main()
