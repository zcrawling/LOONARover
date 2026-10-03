"""Exercise the Pi USB command/telemetry handshake without rover hardware."""

import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


try:
    import termios  # noqa: F401
except ModuleNotFoundError:  # Windows host tests do not call open_serial().
    sys.modules["termios"] = types.ModuleType("termios")

path = Path(__file__).resolve().parents[1] / "payload_pca_service.py"
spec = importlib.util.spec_from_file_location("payload_pca_service", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PayloadPcaServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = module.Service("unused.sock", "unused-device", "unused-logs")
        self.events = []
        self.service.broadcast = self.events.append
        self.service.selector = mock.Mock()
        self.sent = []

        def open_serial():
            self.service.serial_fd = 42
            self.service.log_file = io.StringIO()

        self.service.open_serial = open_serial
        self.write_patch = mock.patch.object(module.os, "write", side_effect=self.write)
        self.close_patch = mock.patch.object(module.os, "close")
        self.write_patch.start()
        self.close_patch.start()
        self.addCleanup(self.write_patch.stop)
        self.addCleanup(self.close_patch.stop)

    def write(self, fd, data):
        self.assertEqual(fd, 42)
        self.sent.append(data)
        return len(data)

    def receive(self, text):
        with mock.patch.object(module.os, "read", return_value=text.encode("ascii")):
            self.service.serial_event()

    def test_each_manual_start_stop_yields_one_station_without_power_switch(self):
        self.service.start(7)
        self.assertEqual(self.sent, [b"START\n"])
        self.assertIn("STATE,7,STARTING,reinitializing", self.events)
        self.receive("CTRL,START,1\n100,1,2,3\n")
        self.assertIn("STATE,7,RUNNING,station_01", self.events)

        self.service.stop(8)
        self.assertEqual(self.sent[-1], b"STOP\n")
        self.assertEqual(self.service.serial_fd, 42)
        self.assertIn("STATE,8,STOPPING,station_01", self.events)
        self.receive("PCA,DEMO_ONLY_260927,1,1000,6000,10,10,1,34.0,27.0,28.0,0.1,0.2,0.3,0,DEMO_ONLY\n"
                     "CTRL,STOP,1\n")
        self.assertEqual(self.service.serial_fd, None)
        self.assertTrue(any(event.startswith("PCA,1,34.0,27.0,28.0,") for event in self.events))
        self.assertIn("STATE,8,IDLE,station_01_complete", self.events)

        self.service.start(9)
        self.receive("CTRL,START,2\n")
        self.assertIn("STATE,9,RUNNING,station_02", self.events)

    def test_stop_ack_without_pca_is_an_error(self):
        self.service.start(7)
        self.receive("CTRL,START,1\n")
        self.service.stop(8)
        self.receive("CTRL,STOP,1\n")
        self.assertIn("STATE,8,ERROR,STOP:missing_pca_or_bad_station", self.events)
        self.assertNotIn("STATE,8,IDLE,station_01_complete", self.events)


if __name__ == "__main__":
    unittest.main()
