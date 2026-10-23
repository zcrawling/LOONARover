import unittest
from unittest.mock import patch

from cli.session_console import handle


class ConsoleTests(unittest.TestCase):
    def test_obj_toggles_using_local_api(self):
        with patch('cli.session_console.request', return_value={'ok':True, 'text':'OBJ OFF'}) as request:
            handle('obj\n')
            handle(' OBJ \n')
            self.assertEqual(request.call_count, 2)
            request.assert_called_with({'action':'obj'}, timeout=2)

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

    def test_exposure_commands_use_selected_backend_camera_action(self):
        cases=[('exposure',{'operation':'status'}),
               ('exposure +',{'operation':'add','value':.5}),
               ('exposure -',{'operation':'add','value':-.5}),
               ('exposure +1.5',{'operation':'set','value':1.5}),
               ('exposure auto',{'operation':'auto'}),
               ('exposure backlight',{'operation':'backlight'})]
        for line,query in cases:
            with self.subTest(line=line),patch('cli.session_console.request',return_value={'text':'ok'}) as call:
                handle(line)
                call.assert_called_once_with(dict(action='camera',**query),timeout=10)

    def test_invalid_exposure_sends_nothing(self):
        for line in ('exposure nan','exposure inf','exposure 4','exposure 1 2'):
            with self.subTest(line=line),patch('cli.session_console.request') as call:
                handle(line);call.assert_not_called()
