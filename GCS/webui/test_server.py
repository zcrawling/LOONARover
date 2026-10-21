import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from webui.server import Server


class WebInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.server = Server(('127.0.0.1', 0))
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, token, command='STOP', **fields):
        return urllib.request.urlopen(urllib.request.Request(
            self.url + '/api/command', data=json.dumps({'command': command, **fields}).encode(),
            headers={'Origin': self.url, 'X-GCS-Token': token,
                     'Content-Type': 'application/json'}))

    def test_command_forwarded_once(self):
        with patch('webui.server.request', return_value={'ok': True}) as backend:
            with self.post(self.server.token) as response:
                self.assertTrue(json.load(response)['ok'])
            backend.assert_called_once_with({'action': 'command', 'command': 'STOP'})

    def test_turns_accept_full_slider_range_and_clamp_excess(self):
        with patch('webui.server.request', return_value={'ok': True}) as backend:
            for command in ('LEFT', 'RIGHT'):
                for value, expected in ((0.2, 0.2), (1.01, 1.01), (3.8, 3.8),
                                        (10, 3.8), (-1, 0)):
                    with self.subTest(command=command, value=value):
                        backend.reset_mock()
                        with self.post(self.server.token, command, angular_speed_radps=value) as response:
                            self.assertEqual(response.status, 200)
                        backend.assert_called_once_with(
                            dict(action='command', command=command, angular_speed_radps=expected))

    def test_linear_speed_clamps_to_wheel_limit(self):
        with patch('webui.server.request', return_value={'ok': True}) as backend:
            with self.post(self.server.token, 'FORWARD', linear_speed_mps=1) as response:
                self.assertEqual(response.status, 200)
            backend.assert_called_once_with(
                dict(action='command', command='FORWARD', linear_speed_mps=0.4))

    def test_invalid_speeds_never_reach_backend(self):
        with patch('webui.server.request') as backend:
            for field in ('linear_speed_mps', 'angular_speed_radps'):
                for value in (True, '1', [], float('nan'), float('inf'), -float('inf')):
                    with self.subTest(field=field, value=value):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            self.post(self.server.token, 'LEFT', **{field: value})
                        self.assertEqual(error.exception.code, 400)
            backend.assert_not_called()

    def test_reaction_settings_forwarded_once(self):
        body = {'command':'REACTION_LEFT','reaction_settings':{'left_first_offset':30}}
        with patch('webui.server.request',return_value={'ok':True}) as backend:
            with urllib.request.urlopen(urllib.request.Request(self.url+'/api/command',
                    data=json.dumps(body).encode(),headers={'Origin':self.url,
                    'X-GCS-Token':self.server.token,'Content-Type':'application/json'})) as response:
                self.assertTrue(json.load(response)['ok'])
            backend.assert_called_once_with(dict(action='command',**body))

    def test_nonfinite_payload_state_remains_readable_and_stop_works(self):
        state = {'connection': 'CONNECTED', 'payload_sample':
                 {'values': {'IR': float('nan'), 'novelty': float('inf')}}}
        def reject_constant(value):
            raise ValueError(value)
        with patch('webui.server.request', return_value=state):
            with urllib.request.urlopen(self.url + '/api/state') as response:
                data = json.loads(response.read(), parse_constant=reject_constant)
            self.assertEqual(data['connection'], 'CONNECTED')
            self.assertIsNone(data['payload_sample']['values']['IR'])
            self.assertIsNone(data['payload_sample']['values']['novelty'])
        with patch('webui.server.request', return_value={'ok': True}):
            with self.post(self.server.token) as response:
                self.assertTrue(json.load(response)['ok'])

    def test_payload_station_buttons_reach_backend(self):
        with patch('webui.server.request', return_value={'ok': True}) as backend:
            for command in ('PAYLOAD_START', 'PAYLOAD_STOP'):
                with self.subTest(command=command), self.post(self.server.token, command) as response:
                    self.assertTrue(json.load(response)['ok'])
            self.assertEqual(backend.call_args_list, [
                unittest.mock.call({'action': 'command', 'command': 'PAYLOAD_START'}),
                unittest.mock.call({'action': 'command', 'command': 'PAYLOAD_STOP'}),
            ])

    def test_invalid_token_never_reaches_backend(self):
        with patch('webui.server.request') as backend:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post('invalid')
            self.assertEqual(error.exception.code, 403)
            backend.assert_not_called()

    def test_payload_commands_forwarded_once(self):
        for command in ('PAYLOAD_START', 'PAYLOAD_STOP'):
            with self.subTest(command=command):
                with patch('webui.server.request', return_value={'ok': True}) as backend:
                    with self.post(self.server.token, command) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(json.load(response)['ok'])
                    backend.assert_called_once_with({'action': 'command', 'command': command})

    def test_backend_failure_is_not_retried(self):
        with patch('webui.server.request', side_effect=OSError('offline')) as backend:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(self.server.token)
            self.assertEqual(error.exception.code, 502)
            self.assertEqual(backend.call_count, 1)


if __name__ == '__main__':
    unittest.main()
