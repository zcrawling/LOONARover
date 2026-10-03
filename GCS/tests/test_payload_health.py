import struct
import time
import unittest
from unittest.mock import patch
from backend.real_app import RealState, GroundLinkConnection

class PayloadHealthTests(unittest.TestCase):
    def setUp(self):
        self.state=RealState('rover'); self.state.connection='CONNECTED'
        self.connection=GroundLinkConnection('rover',7443,self.state)

    def event(self,text):
        source=b'payload-health'
        encoded=text.encode()
        payload=struct.pack('<QBIBH',1000,0,0x5005,len(source),len(encoded))+source+encoded
        self.connection.handle(0x8006,payload)

    def test_online_with_failed_sensor_and_stale_without_new_packets(self):
        self.event('HEALTH,1,1,1,MEASURING,2,5,10,500,20,0000000000000001')
        v=self.state.snapshot()['status']['values']
        self.assertEqual(v['Payload MCU 연결'],'ONLINE')
        self.assertEqual(v['Payload MLX90614'],'미확인/오류')
        self.assertEqual(v['Payload LIS3MDL'],'정상')
        self.state.payload_health_at=time.monotonic()-4
        self.assertEqual(self.state.snapshot()['status']['values']['Payload MCU 연결'],'OFFLINE')

    def test_service_absent_is_offline(self):
        self.event('HEALTH,1,0,0,UNAVAILABLE,0,0,4294967295,4294967295,0,0000000000000000')
        self.assertEqual(self.state.values['Payload 서비스'],'OFFLINE')

    def test_legacy_mcu2_does_not_overwrite_ascii_health(self):
        self.event('HEALTH,1,1,1,IDLE,1,7,10,500,20,0000000000000001')
        with patch('backend.real_app.decode_payload',return_value={'role':'payload','online':False}):
            self.connection.handle(0x8007,b'')
        self.assertEqual(self.state.values['Payload MCU 연결'],'ONLINE')

    def test_malformed_health_never_marks_online(self):
        self.event('HEALTH,1,1,1,IDLE,1,99,10,500,20,0000000000000001')
        self.assertFalse(self.state.payload_ascii)

    def test_disconnect_marks_offline(self):
        self.event('HEALTH,1,1,1,IDLE,1,7,10,500,20,0000000000000001')
        self.state.connection='RECONNECTING'
        self.assertEqual(self.state.snapshot()['status']['values']['Payload MCU 연결'],'OFFLINE')

if __name__=='__main__': unittest.main()
