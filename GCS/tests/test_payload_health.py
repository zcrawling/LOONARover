import struct
import asyncio
import json
import time
import unittest
from unittest.mock import patch
from backend.real_app import RealState, GroundLinkConnection

class PayloadHealthTests(unittest.TestCase):
    def setUp(self):
        self.state=RealState('rover'); self.state.connection='CONNECTED'
        self.connection=GroundLinkConnection('rover',7443,self.state)

    def event(self,text, source=b'payload-health'):
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

    def test_invalid_station_is_json_safe_and_does_not_block_stop(self):
        from unittest.mock import Mock, AsyncMock
        from backend.json_safe import dumps
        self.event('STATE,8,STOPPING,station_01', b'payload-pca')
        # The real MLX wiring failure produces this PCA summary.
        self.event('PCA,1,nan,nan,nan,nan,nan,nan,0,INVALID_STATION,DEMO_ONLY_260927',
                   b'payload-pca')
        self.event('STATE,8,IDLE,station_01_complete', b'payload-pca')
        snapshot = self.state.snapshot()
        json.dumps(snapshot, allow_nan=False)
        value = snapshot['payload_sample']['values']['비접촉 표면온도계']
        self.assertIsNone(value['value'])
        self.assertEqual(value['status'], '측정 오류')
        self.assertEqual(snapshot['status']['payload']['state'], 'IDLE')
        self.assertEqual(snapshot['connection'], 'CONNECTED')
        self.connection.writer = Mock(drain=AsyncMock())
        self.assertTrue(asyncio.run(self.connection.command('STOP'))['ok'])
        self.assertEqual(struct.unpack_from('<4sHHII', self.connection.writer.write.call_args[0][0])[2], 1)
        # Other sensor NaNs must also never poison the state response.
        self.state.values['other_sensor'] = float('inf')
        self.assertIsNone(json.loads(dumps(self.state.snapshot()))['status']['values']['other_sensor'])

    def test_malformed_pca_preserves_previous_sample_and_accepts_following_health(self):
        self.event('PCA,1,10,20,30,0,1,1,0,DEMO_ONLY,model', b'payload-pca')
        sample = self.state.payload_sample
        self.event('PCA,1,10,20,30,0,1,1,inf,DEMO_ONLY,model', b'payload-pca')
        self.assertIs(self.state.payload_sample, sample)
        self.event('HEALTH,1,1,1,IDLE,1,5,10,500,20,0000000000000001')
        self.assertEqual(self.state.values['Payload MCU 연결'], 'ONLINE')

if __name__=='__main__': unittest.main()
