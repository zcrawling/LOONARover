import io
import json
import unittest
from unittest.mock import patch
from cli.xbox_control import Output


class ControllerLogTests(unittest.TestCase):
    def test_commands_and_stop_have_issue_and_response_timestamps(self):
        log = io.StringIO()
        output = Output(dry_run=True, event_log=log)
        output.send('MANUAL', (.1, .2))
        output.stop()
        rows = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual([r['event'] for r in rows], ['issued','response','issued','response'])
        self.assertEqual(rows[0]['command']['linear_mps'], .1)
        self.assertEqual(rows[2]['command']['command'], 'STOP')
        self.assertGreaterEqual(rows[1]['response_epoch_ns'], rows[0]['laptop_epoch_ns'])

    def test_failed_transport_preserves_attempt_and_allows_stop(self):
        log = io.StringIO()
        output = Output(event_log=log)
        with patch('cli.xbox_control.request', side_effect=OSError('disconnected')):
            with self.assertRaises(OSError):
                output.send('MANUAL', (.1, 0.))
        self.assertTrue(output.active)
        self.assertEqual(json.loads(log.getvalue())['event'], 'issued')
        with patch('cli.xbox_control.request', return_value={'ok':True}) as request:
            output.stop()
            self.assertEqual(request.call_args.args[0]['command'], 'STOP')

    def test_logging_failure_cannot_block_stop_delivery(self):
        class FullDisk:
            def write(self, *_):
                raise OSError('disk full')
        output = Output(event_log=FullDisk())
        output.active = True
        with patch('cli.xbox_control.request', return_value={'ok':True}) as request:
            output.stop()
        self.assertEqual(request.call_args.args[0]['command'], 'STOP')
        self.assertFalse(output.active)
