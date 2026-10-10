import json
from pathlib import Path
import tempfile
import unittest

from .monitor import StatusPublisher
from .link import Link
from .test_v2 import FakeSerial


class MonitorTests(unittest.TestCase):
    def test_snapshot_publish_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            publisher = StatusPublisher('control', tmp).start()
            publisher.update(online=True, temperature_c=44)
            publisher.update(online=False)
            publisher.close()
            data = json.loads((Path(tmp)/'control.json').read_text())
            self.assertFalse(data['online'])
            self.assertEqual(data['temperature_c'], 44)
            self.assertGreater(data['updated_ns'], 0)
            self.assertIn('boot_id', data)

    def test_serial_timestamps_only_after_actual_io(self):
        link = Link(dict(device='fake', role_id=1, uid_int=1), FakeSerial)
        try:
            self.assertIsNotNone(link.last_rx_ns)
            self.assertIsNotNone(link.last_tx_ns)
            last_rx = link.last_rx_ns
            link.poll()  # No bytes available.
            self.assertEqual(link.last_rx_ns, last_rx)
        finally:
            link.close()
