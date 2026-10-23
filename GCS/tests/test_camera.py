import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from backend.camera import control


class CameraRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_rover_and_request_are_sent_over_existing_ssh(self):
        process=Mock(returncode=0)
        process.communicate=AsyncMock(return_value=(json.dumps({'ok':True,'text':'EV +1.5'}).encode(),b''))
        with patch('backend.camera.ssh_command',return_value=(['test-ssh'],{})) as ssh, \
             patch('backend.camera.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
            result=await control('192.0.2.99', {'operation':'set','value':1.5})
        self.assertTrue(result['ok'])
        self.assertEqual(ssh.call_args.args[0],'192.0.2.99')
        self.assertIn(b"'value': 1.5",process.communicate.call_args.args[0])
        process.kill.assert_not_called()

    async def test_timeout_is_failure_and_child_is_reaped(self):
        process=Mock(returncode=None)
        process.communicate=AsyncMock(side_effect=asyncio.TimeoutError)
        process.wait=AsyncMock()
        with patch('backend.camera.ssh_command',return_value=(['test-ssh'],{})), \
             patch('backend.camera.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
            result=await control('192.0.2.99',{'operation':'status'})
        self.assertFalse(result['ok'])
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()
