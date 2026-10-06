import signal
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from .ros_samples import RosSamples


class RosSamplesTests(unittest.TestCase):
    def test_custom_ros_launcher_owns_and_stops_its_process_group(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            child = Mock(pid=12345)
            child.poll.return_value = None
            publisher = RosSamples(runtime, runtime / "control.json",
                                   {"LOONAR_ROS_SAMPLE_LAUNCHER": "/test/start_auto_ros.sh"})
            with patch("mcu_v2.ros_samples.subprocess.Popen", return_value=child) as spawn:
                publisher.start()
            self.assertEqual(spawn.call_args.args[0][1], "/test/start_auto_ros.sh")
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])
            with patch("mcu_v2.ros_samples.os.killpg") as stop:
                publisher.close()
            stop.assert_called_once_with(12345, signal.SIGINT)
            child.wait.assert_called_once_with(timeout=10)

    def test_sample_forwarding_without_starting_recorder(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            child = Mock()
            child.poll.return_value = None
            publisher = RosSamples(runtime, runtime / "control.json", {})
            consumer = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            consumer.bind(str(publisher.sample_path))
            consumer.settimeout(1)
            try:
                with patch("mcu_v2.ros_samples.subprocess.Popen", return_value=child) as spawn:
                    publisher.start()
                spawn.assert_called_once()
                self.assertEqual(spawn.call_args.args[0],
                                 ["bash", str(publisher.tools / "run-bench-sensors.sh"),
                                  str(runtime / "control.json"), str(publisher.sample_path)])
                raw = b'{"kind":33,"seq":1,"payload":"example"}'
                publisher.forward(raw)
                self.assertEqual(consumer.recv(4096), raw)
                self.assertEqual(publisher.forward_errors, 0)
                self.assertFalse((runtime / "rosbag.log").exists())
            finally:
                publisher.close()
                consumer.close()
            child.send_signal.assert_called_once_with(signal.SIGTERM)
            child.kill.assert_not_called()

    def test_publisher_exit_and_missing_consumer_are_reported_only(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            child = Mock()
            child.poll.return_value = 1
            publisher = RosSamples(runtime, runtime / "control.json", {})
            try:
                with patch("mcu_v2.ros_samples.subprocess.Popen", return_value=child):
                    publisher.start()
                with self.assertLogs(level="ERROR") as logs:
                    publisher.poll()
                    publisher.poll()
                self.assertEqual(len(logs.output), 1)
                child.send_signal.assert_not_called()
                with self.assertLogs(level="WARNING"):
                    publisher.forward(b"no consumer yet")
                self.assertEqual(publisher.forward_errors, 1)
            finally:
                publisher.close()


if __name__ == "__main__":
    unittest.main()
