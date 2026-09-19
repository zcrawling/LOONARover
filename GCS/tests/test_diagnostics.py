import io
import json
import re
import unittest
from unittest.mock import patch
from cli.diagnostics import Screen, REMOTE, backend_rows, probe

class Terminal(io.StringIO):
    def isatty(self):
        return True

class DiagnosticsTests(unittest.TestCase):
    def test_footer_stays_below_history_and_changes_are_persistent(self):
        stream, log = Terminal(), io.StringIO()
        screen = Screen(stream, log, '192.168.1.50')
        checked = '2026-09-19T10:00:00+09:00'
        screen.update('GROUNDLINK', '연결됨', 'TCP 연결', checked)
        screen.draw()
        screen.update('GROUNDLINK', '끊김', 'EOF', checked)
        screen.draw()
        text = stream.getvalue()
        self.assertIn('\033[15A', text)
        self.assertLess(text.rindex('연결됨 → 끊김'), text.rindex('현재 상태'))
        records = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual(records[-1]['before'], '연결됨')
        self.assertEqual(records[-1]['status'], '끊김')

    def test_rx_counts_are_not_logged_but_new_command_results_are(self):
        screen = Screen(io.StringIO(), io.StringIO(), 'host')
        screen.update('DATA RECEIVED', '정상', 'RX 1')
        screen.update('DATA RECEIVED', '정상', 'RX 2')
        screen.update('COMMAND', '처리 완료', 'STOP #1')
        screen.update('COMMAND', '처리 완료', 'STOP #2')
        self.assertEqual(len(screen.log.getvalue().splitlines()), 3)

    def test_backend_reuses_local_api_and_rejects_mock(self):
        with patch('cli.diagnostics.request', return_value={'source': 'MOCK'}):
            with self.assertRaises(ValueError):
                backend_rows('host')
        with patch('cli.diagnostics.request', return_value={
                'source': 'REAL ROVER / host', 'connection': 'CONNECTED',
                'last_rx_age': 0.3, 'rx_messages': 10, 'requests': [], 'events': []}) as api:
            rows = backend_rows('host')
            api.assert_called_once_with({'action': 'state'})
            self.assertEqual(rows['DATA RECEIVED'], (0.3, True, 10))

    def test_probe_ssh_failure_does_not_claim_driver_failure(self):
        import subprocess
        ping = subprocess.CompletedProcess([], 0, '', '')
        ssh = subprocess.CompletedProcess([], 255, '', 'Permission denied')
        with patch('cli.diagnostics.subprocess.run', side_effect=[ping, ssh]), \
             patch('cli.diagnostics.socket.create_connection'):
            rows = probe('host', 'user@host', None)
        self.assertEqual(rows['SSH PORT'][0], '정상')
        self.assertEqual(rows['SSH LOGIN'][0], '실패')
        self.assertEqual(rows['ROVER DRIVER'][0], '확인 불가')
        for pattern in ('/[l]imo_base/lib/limo_base/limo_base', '/[v]ehicle_gatewayd( |$)'):
            self.assertIsNone(re.search(pattern, REMOTE))

if __name__ == '__main__':
    unittest.main()
