import struct
import unittest
from .imu import decode_imu
from .wire import Frame, Kind, Parser

class ImuTests(unittest.TestCase):
    def test_reports(self):
        for sensor,n in ((1,3),(2,3),(4,3),(5,4),(6,3)):
            p=struct.pack('<4BQ5fI',sensor,3,255,0,123456,1,-2,3,1,0,2)
            frame=Frame(1,Kind.IMU,boot=3,session=4,sequence=10,stamp_us=123456,payload=p)
            parser=Parser()
            encoded=frame.encode()
            self.assertEqual(parser.feed(encoded[:17]),[])
            frames=parser.feed(encoded[17:])
            self.assertEqual(frames,[frame])
            v=decode_imu(frames[0].payload)
            self.assertEqual(len(v['values']),n)
            self.assertEqual(v['sequence'],255)
            self.assertEqual(v['reinitializations'],2)
            self.assertEqual(v['sensor_or_receipt_us'],123456)
    def test_invalid(self):
        for p in (b'',struct.pack('<4BQ5fI',2,0,0,0,0,float('nan'),0,0,0,0,0)):
            with self.assertRaises(ValueError): decode_imu(p)
