"""Payload handshake, failure recovery and a real pseudo-terminal transport."""
import importlib.util
import os
import pty
import tempfile
import time
from pathlib import Path
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('payload_pca_service', Path(__file__).resolve().parents[1] / 'payload_pca_service.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PCA = 'PCA,DEMO_ONLY_260927,1,1000,6000,10,10,1,34.0,27.0,28.0,0.1,0.2,0.3,0,DEMO_ONLY'

class PayloadServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = module.Service('unused', 'unused', self.temp.name)
        self.events, self.sent = [], []
        self.s.broadcast = self.events.append
        self.s.send_serial = self.sent.append
        self.s.close_serial = mock.Mock()
        self.addCleanup(self.s.close_capture)
        self.addCleanup(self.s.selector.close)
        self.health()
        self.finish('RESULT', error='no_result')

    def health(self, state='IDLE', boot=1, mask=7):
        nonce = '55'
        self.s.polls[nonce] = time.monotonic()
        self.s.handle_line(f'HEALTH,1,{nonce},0000000000000001,{boot},{state},1,100,{mask},500,12,payload-1')

    def finish(self, op, station=1, error=None):
        nonce = next(k for k,v in self.s.pending.items() if v[1] == op)
        self.s.handle_line(f'ERROR,{nonce},{error}' if error else f'DONE,{nonce},{op},{station}')

    def test_start_stop_keeps_port_open_and_records_full_result(self):
        self.s.start(7)
        self.assertTrue(self.sent[-1].endswith(',START'))
        self.finish('START')
        self.health('MEASURING')
        self.s.stop(8)
        self.s.record(PCA)
        self.s.handle_line(PCA)
        self.finish('STOP')
        self.assertFalse(self.s.running)
        self.assertIsNone(self.s.log_file)
        self.s.close_serial.assert_not_called()
        self.assertTrue(any(e.startswith('PCA,1,34,27,28,') for e in self.events))
        self.assertIn(PCA, next(Path(self.temp.name).glob('*.csv')).read_text())
        self.assertIn('STATE,8,IDLE,station_01_complete',self.events)

    def test_missing_pca_does_not_complete_stop(self):
        self.s.start(7); self.finish('START'); self.s.stop(8)
        with self.assertRaises(ValueError): self.finish('STOP')
        self.assertTrue(any(v[1]=='STOP' for v in self.s.pending.values()))
        self.assertFalse(any('complete' in e for e in self.events))

    def test_duplicate_request_does_not_send_start_again(self):
        self.s.start(7); count=len(self.sent)
        self.s.start(7)
        self.assertEqual(len(self.sent),count)
        self.s.stop(7)
        self.assertIn('ERROR,7,COMMAND,request_conflict',self.events)

    def test_stop_during_start_cancels_without_pca(self):
        self.s.start(7); self.s.stop(8)
        self.finish('START', error='cancelled'); self.finish('STOP',station=0)
        self.assertFalse(self.s.pending)
        self.assertIn('STATE,8,IDLE,station_00_complete',self.events)

    def test_offline_start_never_reaches_usb(self):
        self.s.last_health=time.monotonic()-4
        count=len(self.sent); self.s.start(7)
        self.assertEqual(len(self.sent),count)
        self.assertIn('ERROR,7,START,mcu_offline',self.events)

    def test_status_must_match_recent_poll(self):
        before=self.s.last_health
        self.s.handle_line('HEALTH,1,999,0000000000000001,1,IDLE,1,100,7,500,12,payload-1')
        self.assertEqual(self.s.last_health,before)
        self.s.polls['999']=time.monotonic()-4
        self.s.handle_line('HEALTH,1,999,0000000000000001,1,IDLE,1,100,7,500,12,payload-1')
        self.assertEqual(self.s.last_health,before)

    def test_failed_sensor_is_still_online(self):
        self.health(mask=0)
        self.assertTrue(self.s.online())
        self.assertEqual(self.s.health['mask'],0)

    def test_reboot_invalidates_pending_command(self):
        self.s.start(7); self.health(boot=2)
        self.assertIn('ERROR,7,STATION,START:mcu_reboot',self.events)
        self.assertTrue(all(v[1]=='RESULT' for v in self.s.pending.values()))

    def test_reconnect_queries_result_without_restarting_measurement(self):
        self.s.last_health=None; self.sent.clear()
        self.health('MEASURING')
        self.assertEqual(len(self.sent),1)
        self.assertTrue(self.sent[0].endswith(',RESULT'))
        self.assertTrue(self.s.running)

    def test_last_result_recovery(self):
        self.s.last_health=None; self.health()
        self.s.handle_line(PCA); self.finish('RESULT')
        self.assertEqual(self.s.completed_station,1)
        self.assertIn(PCA, next(Path(self.temp.name).glob('*.csv')).read_text())
        self.assertTrue(any(e.startswith('PCA,1,') for e in self.events))

    def test_disk_failure_does_not_disconnect_mcu(self):
        self.s.log_file=mock.Mock()
        self.s.log_file.write.side_effect=OSError('disk full')
        self.s.record('1,2,3')
        self.assertTrue(self.s.online())
        self.assertTrue(self.s.log_error)
        self.assertIn('ERROR,0,RECORD,write_failed',self.events)

    def test_bounded_event_and_bad_numbers(self):
        with self.assertRaises(ValueError): self.s.handle_line(PCA.replace('34.0','inf'))
        self.s.handle_line(PCA.replace('34.0','1e30'))
        self.assertLessEqual(len(self.s.result[1]),127)

    def test_command_timeout_is_unknown_not_completed(self):
        self.s.start(7)
        for nonce,(request,op,_) in list(self.s.pending.items()): self.s.pending[nonce]=(request,op,0)
        self.s.next_open=self.s.next_health=float('inf')
        self.s.check_deadline()
        self.assertIn('ERROR,7,STATION,START:result_unknown',self.events)

class PtyTransportTests(unittest.TestCase):
    def test_split_lines_status_and_exclusive_port(self):
        master, slave=pty.openpty()
        with tempfile.TemporaryDirectory() as directory:
            s=module.Service(Path(directory)/'socket',os.ttyname(slave),directory)
            other=module.Service(Path(directory)/'other',os.ttyname(slave),directory)
            events=[]; s.broadcast=events.append
            try:
                s.check_deadline()
                command=os.read(master,512).decode().strip()
                self.assertTrue(command.startswith('STATUS,'))
                nonce=command.split(',')[1]
                with self.assertRaises(BlockingIOError): other.open_serial()
                line=f'HEALTH,1,{nonce},0000000000000001,1,IDLE,1,10,7,4294967295,0,payload-1\n'.encode()
                os.write(master,line[:15]); s.serial_event()
                self.assertFalse(s.online())
                os.write(master,line[15:]); s.serial_event()
                self.assertTrue(s.online())
                self.assertIn('CMD,',os.read(master,512).decode())
                s.last_health=time.monotonic()-4
                s.check_deadline()
                self.assertIsNone(s.serial_fd)
                self.assertTrue(any(e.startswith('HEALTH,1,0,') for e in events))
            finally:
                s.close_capture(); s.close_serial(); s.selector.close(); other.selector.close()
                os.close(master); os.close(slave)

if __name__=='__main__': unittest.main()
