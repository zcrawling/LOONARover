import shlex
import unittest
import subprocess
import sys
from loonar_apriltag.run_distance_test import reached, remote_command, TrackingGate, resolve_host, remember_host
import tempfile
from pathlib import Path


class DistanceTests(unittest.TestCase):
    def test_hotspot_host_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'host.json'
            self.assertEqual(resolve_host(config=config),'wego@192.168.0.7')
            remember_host('wego@172.20.10.2',config)
            self.assertEqual(resolve_host(config=config),'wego@172.20.10.2')
            self.assertEqual(resolve_host(ip='192.168.43.10',config=config),'wego@192.168.43.10')
            self.assertEqual(resolve_host(host='wego-NUC12WSKi7.local',config=config),'wego@wego-NUC12WSKi7.local')
            for host in ['-oProxyCommand=bad','host;bad','user@host extra']:
                with self.assertRaises(ValueError):resolve_host(host=host,config=config)
    def test_dropout_recovery_and_persistent_loss(self):
        g=TrackingGate(.3,3,5)
        self.assertEqual(g.update(True,0),'PAUSE')
        self.assertEqual(g.update(True,.1),'PAUSE')
        self.assertEqual(g.update(True,.2),'RESUME')
        self.assertEqual(g.update(False,.3),'RESUME')
        self.assertEqual(g.update(False,.4),'RESUME')
        for t in [.45,.5,.55]:self.assertEqual(g.update(True,t),'RESUME')
        self.assertEqual(g.update(False,1),'RESUME')
        self.assertEqual(g.update(False,1.31),'PAUSE')
        self.assertEqual(g.update(True,1.4),'PAUSE')
        self.assertEqual(g.update(True,1.5),'PAUSE')
        self.assertEqual(g.update(True,1.6),'RESUME')
        g.update(False,2)
        self.assertEqual(g.update(False,7.1),'STOP')

    def test_supervisor_forwards_pause_resume_and_stop(self):
        shell=shlex.split(remote_command(1,.05,'test'))[2]
        command=shlex.split(shell.split(' && exec ',1)[1])
        child='import sys; print(sys.stdin.read(),end="")'
        result=subprocess.run([sys.executable,'-c',command[3],sys.executable,'-c',child],
                              input='RESUME\nPAUSE\nRESUME\nSTOP\n',text=True,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'RESUME\nPAUSE\nRESUME\nSTOP\n')
    def test_forward_threshold_is_not_elapsed_time(self):
        self.assertFalse(reached(1.99,2))
        self.assertTrue(reached(2,2))
        self.assertTrue(reached(2.01,2))
        self.assertFalse(reached(-2,2))
        self.assertFalse(reached(float('nan'),2))

    def test_remote_runner_uses_external_stop_and_compilable_supervisor(self):
        shell = shlex.split(remote_command(2,.05,'test'))[2]
        command = shlex.split(shell.split(' && exec ',1)[1])
        compile(command[3],'supervisor','exec')
        compile(command[7],'child','exec')
        self.assertIn('--external-stop',command)
        self.assertEqual(command[command.index('--duration')+1],'40.0')
        self.assertIn('SIGINT',command[3])


if __name__=='__main__':unittest.main()
