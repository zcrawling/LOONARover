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

    def post(self, token):
        return urllib.request.urlopen(urllib.request.Request(
            self.url + '/api/command', data=b'{"command":"STOP"}',
            headers={'Origin': self.url, 'X-GCS-Token': token,
                     'Content-Type': 'application/json'}))

    def test_command_forwarded_once(self):
        with patch('webui.server.request', return_value={'ok': True}) as backend:
            with self.post(self.server.token) as response:
                self.assertTrue(json.load(response)['ok'])
            backend.assert_called_once_with({'action': 'command', 'command': 'STOP'})

    def test_invalid_token_never_reaches_backend(self):
        with patch('webui.server.request') as backend:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post('invalid')
            self.assertEqual(error.exception.code, 403)
            backend.assert_not_called()

    def test_backend_failure_is_not_retried(self):
        with patch('webui.server.request', side_effect=OSError('offline')) as backend:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(self.server.token)
            self.assertEqual(error.exception.code, 502)
            self.assertEqual(backend.call_count, 1)


if __name__ == '__main__':
    unittest.main()
