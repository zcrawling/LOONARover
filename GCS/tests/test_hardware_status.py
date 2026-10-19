import json
from pathlib import Path
import socket
import tempfile
import time
import unittest

from backend.hardware_status import HardwareStatus


class HardwareStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / 'hardware.json'
        self.owner = HardwareStatus('127.0.0.1', bind='127.0.0.1', port=0, cache=self.cache)
        self.owner.poll()
        self.port = self.owner.sock.getsockname()[1]
        self.reader = HardwareStatus('127.0.0.1', bind='127.0.0.1', port=self.port, cache=self.cache)
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def tearDown(self):
        self.owner.close()
        self.reader.close()
        self.sender.close()
        self.tmp.cleanup()

    def send(self, seq=1, session='boot1', **changes):
        packet = dict(schema=1, kind='hardware', source='127.0.0.1', seq=seq,
                      stamp_ns=time.time_ns(), pi_boot_id='pi', publisher_session=session,
                      data=dict(input_voltage_v=5.05, wireless=[dict(signal_dbm=-60)]))
        packet.update(changes)
        self.sender.sendto(json.dumps(packet).encode(), ('127.0.0.1', self.port))

    def test_existing_port_owner_shares_data_without_stealing_packets(self):
        self.send()
        self.assertEqual(self.owner.snapshot()['data']['input_voltage_v'], 5.05)
        self.assertEqual(self.reader.snapshot()['data']['wireless'][0]['signal_dbm'], -60)
        self.assertIsNone(self.reader.sock)

    def test_stale_cache_and_receiver_never_supply_live_values(self):
        self.send()
        self.owner.poll()
        self.owner.received -= 5
        self.owner._save()
        self.assertIsNone(self.owner.snapshot()['data'])
        self.assertIsNone(self.reader.snapshot()['data'])

    def test_sequences_sessions_sender_and_kind(self):
        self.send(seq=3)
        self.assertEqual(self.owner.snapshot()['sequence'], 3)
        self.send(seq=2)
        self.send(seq=4, source='10.0.0.9')
        self.send(seq=5, kind='communication')
        self.assertEqual(self.owner.snapshot()['sequence'], 3)
        self.send(seq=1, session='boot2')
        self.assertEqual(self.owner.snapshot()['sequence'], 1)

    def test_reader_takes_over_when_owner_exits(self):
        self.reader.poll()
        self.owner.close()
        self.reader.next_bind = 0
        self.reader.poll()
        self.send()
        self.assertEqual(self.reader.snapshot()['data']['input_voltage_v'], 5.05)


if __name__ == '__main__':
    unittest.main()
