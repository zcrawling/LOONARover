import unittest
from unittest.mock import patch

from cli.session_console import handle


class ConsoleTests(unittest.TestCase):
    def test_flip_is_a_local_toggle_not_a_motion_command(self):
        with patch('cli.session_console.request', return_value={'ok':True, 'text':'FLIP ON'}) as request:
            handle('  flip\n')
            handle('FLIP\n')
            self.assertEqual(request.call_count, 2)
            request.assert_called_with({'action':'flip'}, timeout=2)

    def test_unknown_input_and_empty_lines_send_nothing(self):
        with patch('cli.session_console.request') as request:
            handle('\n')
            handle('forward\n')
            request.assert_not_called()

    def test_disconnect_does_not_crash_console(self):
        with patch('cli.session_console.request', side_effect=OSError('disconnected')):
            handle('flip')
