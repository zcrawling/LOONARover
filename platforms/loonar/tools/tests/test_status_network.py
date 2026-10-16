import importlib.util
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'GCS'),str(ROOT/'platforms/loonar/tools')]
from cli.status_udp import decode,render,run
from pi_status_broadcast import Broadcast,DESTINATIONS

class StatusNetworkTests(unittest.TestCase):
    def test_two_peers_receive_both_streams(self):
        sockets=[];ports={}
        try:
            for kind in ('hardware','communication'):
                first=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                first.bind(('127.0.0.1',0));first.settimeout(1);sockets.append((kind,first))
                port=first.getsockname()[1];ports[kind]=port
                other=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                other.bind(('127.0.0.2',port));other.settimeout(1);sockets.append((kind,other))
            sender=Broadcast(('127.0.0.1','127.0.0.2'),ports,'127.0.0.1')
            self.addCleanup(sender.socket.close)
            sender.emit({'cpu_temperature_c':45},{'groundlink':{'gcs_connected':True}})
            for kind,sock in sockets:
                raw,peer=sock.recvfrom(32768);packet=decode(raw,peer,'127.0.0.1')
                self.assertEqual(packet['kind'],kind);self.assertEqual(packet['seq'],1)
            self.assertEqual(sender.dropped,0)
        finally:
            for kind,sock in sockets:sock.close()
    def test_reject_other_sender_and_stale_ui(self):
        packet=dict(schema=1,kind='hardware',source='10.254.254.3',seq=1,stamp_ns=100,
                    data={'cpu_temperature_c':50})
        raw=json.dumps(packet).encode()
        with self.assertRaises(ValueError):decode(raw,('10.254.254.4',123))
        self.assertEqual(decode(raw,('10.254.254.3',123)),packet)
        self.assertIn('50.00','\n'.join(render('hardware',packet,0,0)))
        self.assertNotIn('50.00','\n'.join(render('hardware',packet,5,0)))
    def test_subscriber_never_sends_requests_or_ack(self):
        from unittest.mock import MagicMock
        packet=dict(schema=1,kind='hardware',source='10.254.254.3',seq=1,stamp_ns=100,
                    pi_boot_id='boot',publisher_session='session',data={})
        sock=MagicMock();sock.__enter__.return_value=sock
        sock.recvfrom.return_value=(json.dumps(packet).encode(),('10.254.254.3',123))
        with patch('cli.status_udp.socket.socket',return_value=sock),patch('builtins.print'):
            run('hardware',once=True)
        sock.send.assert_not_called();sock.sendto.assert_not_called();sock.connect.assert_not_called()
    def test_service_restart_resets_sequence(self):
        from unittest.mock import MagicMock
        def packet(seq,session):return json.dumps(dict(schema=1,kind='hardware',source='10.254.254.3',
            seq=seq,stamp_ns=100,pi_boot_id='boot',publisher_session=session,data={})).encode()
        sock=MagicMock();sock.__enter__.return_value=sock
        sock.recvfrom.side_effect=[(packet(100,'first'),('10.254.254.3',1)),(packet(1,'second'),('10.254.254.3',1)),KeyboardInterrupt()]
        printed=[]
        with patch('cli.status_udp.socket.socket',return_value=sock),patch('builtins.print',side_effect=lambda *a,**k:printed.append(a)):
            with self.assertRaises(KeyboardInterrupt):run('hardware')
        self.assertEqual(len(printed),2)
    def test_default_destinations_are_control_and_observer(self):
        self.assertEqual(DESTINATIONS,('10.254.254.2','10.254.254.4'))

if __name__=='__main__':unittest.main()
