import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from loonar_apriltag.ssh_auth import authenticated


class AuthenticationTests(unittest.TestCase):
    @patch('loonar_apriltag.ssh_auth.shutil.which', return_value='/usr/bin/sshpass')
    def test_password_stays_out_of_arguments(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'password';p.write_text('test-only-secret');p.chmod(0o600)
            for tool in ['ssh','scp']:
                command=authenticated(tool,p)
                self.assertEqual(command,['sshpass','-f',str(p),tool])
                self.assertNotIn('test-only-secret',' '.join(command))
            p.chmod(0o644)
            with self.assertRaises(RuntimeError):authenticated('ssh',p)
