"""Backend reuse must preserve rover identity and process ownership."""
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from webui import server


class WebStartupTests(unittest.TestCase):
    def test_same_rover_backend_is_reused_without_owning_it(self):
        children = []
        with patch.object(server, 'request', return_value={
                'source': 'REAL ROVER / 10.254.254.3'}) as request, \
                patch.object(server.subprocess, 'Popen') as spawn:
            server.start_services(Path('config'), children, io.StringIO(), '10.254.254.3')
        spawn.assert_not_called()
        request.assert_called_once_with({'action': 'state'}, timeout=0.5)
        self.assertEqual(children, [])

    def test_different_rover_or_mock_is_not_reused(self):
        for source in ('REAL ROVER / 192.168.0.14', 'MOCK / 예시 데이터', None):
            with self.subTest(source=source), \
                    patch.object(server, 'request', return_value={'source': source}), \
                    patch.object(server.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError, '다른 백엔드'):
                    server.start_services(Path('config'), [], io.StringIO(), '10.254.254.3')
                spawn.assert_not_called()

    def test_absent_or_stale_socket_starts_new_backend(self):
        for error in (FileNotFoundError(), ConnectionRefusedError()):
            with self.subTest(error=type(error).__name__):
                child = Mock()
                child.poll.return_value = None
                children = []
                with patch.object(server, 'request', side_effect=[error, {'source': 'REAL ROVER / rover'}]), \
                        patch.object(server.subprocess, 'Popen', return_value=child) as spawn, \
                        patch.object(server.time, 'sleep'):
                    server.start_services(Path('config'), children, io.StringIO(), 'rover')
                spawn.assert_called_once()
                self.assertEqual(children, [child])

    def test_child_failure_reports_log_location(self):
        child = Mock(returncode=1)
        child.poll.return_value = 1
        with patch.object(server, 'request', side_effect=FileNotFoundError()), \
                patch.object(server.subprocess, 'Popen', return_value=child), \
                patch.object(server.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, r'code=1.*services.log'):
                server.start_services(Path('config'), [], io.StringIO(), 'rover')
