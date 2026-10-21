import signal
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from loonar_fly.auto_processes import AutoProcesses, sensor_commands


class AutoProcessesTests(unittest.TestCase):
    def setUp(self):
        self.spawned = []
        self.spawn_patch = patch('loonar_fly.auto_processes.subprocess.Popen', self.spawn)
        self.signal_patch = patch('loonar_fly.auto_processes.os.killpg')
        self.spawn_patch.start()
        self.signals = self.signal_patch.start()
        self.addCleanup(self.spawn_patch.stop)
        self.addCleanup(self.signal_patch.stop)
        self.manager = AutoProcesses({'sensors': ['sensor-test'], 'terrain': ['terrain-test']}, Mock())

    def spawn(self, command, **kwargs):
        self.assertTrue(kwargs['start_new_session'])
        child = Mock(pid=10000 + len(self.spawned))
        child.poll.return_value = None
        self.spawned.append((command, child))
        return child

    def test_idle_auto_heading_and_duplicate_auto(self):
        self.manager.tick(False, None)
        self.assertFalse(self.spawned)
        self.manager.tick(True, None)
        self.assertEqual(set(self.manager.children), {'sensors', 'terrain'})
        self.manager.tick(True, .4)
        self.assertEqual(len(self.spawned), 3)
        self.assertEqual(self.spawned[-1][0][-2:], ['--heading-target', '0.4'])
        self.manager.tick(True, .8)
        self.assertEqual(len(self.spawned), 3)

    def test_mode_exit_stops_all_groups_and_fast_auto_waits_for_exit(self):
        self.manager.tick(True, .4)
        self.manager.tick(False, None)
        self.assertEqual(self.signals.call_count, 3)
        self.assertTrue(all(c.args[1] == signal.SIGINT for c in self.signals.call_args_list))
        self.manager.tick(True, 1.2)
        self.assertEqual(len(self.spawned), 3)
        for _, child in self.spawned:
            child.poll.return_value = 0
        self.manager.tick(True, 1.2)
        self.assertFalse(self.manager.children)
        self.manager.tick(True, 1.2)
        self.assertEqual(len(self.spawned), 6)
        self.assertEqual(self.spawned[-1][0][-1], '1.2')

    def test_crash_stops_peers_and_does_not_restart_until_rearmed(self):
        self.manager.tick(True, .4)
        self.spawned[0][1].poll.return_value = 1
        self.manager.tick(True, .4)
        self.assertTrue(self.manager.failed)
        self.assertIn('sensors exited (1)', self.manager.failure)
        for _, child in self.spawned:
            child.poll.return_value = 0
        self.manager.tick(True, .4)
        self.manager.tick(True, .4)
        self.assertEqual(len(self.spawned), 3)
        self.manager.rearm()
        self.manager.tick(True, .4)
        self.assertEqual(len(self.spawned), 6)

    def test_stop_during_heading_wait_and_forced_shutdown(self):
        self.manager.tick(True, None)
        self.manager.tick(False, None)
        self.manager.stop_at -= 6
        self.manager.tick(False, None)
        self.assertEqual(set(self.manager.children), {'sensors', 'terrain'})
        self.assertEqual([c.args[1] for c in self.signals.call_args_list][-2:],
                         [signal.SIGKILL, signal.SIGKILL])

    def test_partial_spawn_failure_cleans_up(self):
        with patch('loonar_fly.auto_processes.subprocess.Popen',
                   side_effect=[self.spawn(['sensor-test'], start_new_session=True), OSError('failed')]):
            self.manager.tick(True, .4)
        self.assertTrue(self.manager.failed)
        self.assertEqual(set(self.manager.children), {'sensors'})
        self.signals.assert_called_with(self.spawned[0][1].pid, signal.SIGINT)

    def test_sensor_launch_cannot_duplicate_base_or_start_another_navigator(self):
        command = sensor_commands('/tmp/test.yaml')['sensors']
        for setting in ('run_base_io:=false', 'run_motion:=false', 'run_navigator:=false',
                        'run_adapter:=true', 'run_stationary:=true', 'run_safety:=true'):
            self.assertIn(setting, command)


class RealProcessTests(unittest.TestCase):
    def test_shutdown_removes_descendants_of_a_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / 'helper.pid'
            helper = 'import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(60)'
            launcher = (
                'import subprocess,sys,time,signal; from pathlib import Path; '
                'signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); '
                f'child=subprocess.Popen([sys.executable,"-c",{helper!r}]); '
                f'Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep(60)'
            )
            manager = AutoProcesses({'sensors': [sys.executable, '-c', launcher]},
                                    lambda _: None, stop_timeout=.2)
            try:
                manager.tick(True, None)
                deadline = time.monotonic() + 3
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(pid_file.exists())
                descendant = int(pid_file.read_text())
                manager.close()
                stat = Path(f'/proc/{descendant}/stat')
                deadline = time.monotonic() + 2
                while stat.exists() and stat.read_text().split(') ')[1][0] != 'Z' and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(not stat.exists() or stat.read_text().split(') ')[1][0] == 'Z')
            finally:
                manager.close()

    def test_actual_worker_stops_and_restarts_without_hardware(self):
        manager = AutoProcesses({'sensors': [sys.executable, '-c',
            'import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(60)']},
            lambda _: None, stop_timeout=.1)
        try:
            manager.tick(False, None)
            self.assertFalse(manager.children)
            manager.tick(True, None)
            first = manager.children['sensors']
            time.sleep(.15)
            manager.close()
            self.assertIsNotNone(first.poll())
            self.assertFalse(manager.children)
            manager.tick(True, None)
            self.assertNotEqual(manager.children['sensors'].pid, first.pid)
        finally:
            manager.close()


if __name__ == '__main__':
    unittest.main()
