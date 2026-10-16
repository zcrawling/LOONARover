import sys
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcu_v2.reaction_gateway import ReactionController
from mcu_v2.reaction_wheel import Settings, STATUS
from mcu_v2.wire import Kind, Frame
from mcu_v2.link import Link
from mcu_v2.backend import Gateway, GATEWAY_HEADER

class FakeLink:
    check_result=staticmethod(Link.check_result)
    def __init__(self): self.sent=[]
    def send(self,kind,payload=b''):
        self.sent.append((kind,payload));return len(self.sent)

class Tests(unittest.TestCase):
    def setUp(self):
        self.link=FakeLink();self.events=[]
        self.control=ReactionController(self.link,self.events.append)
        self.request=bytes([2])+Settings(right_first_offset=30).encode()
    def result(self,code=0):
        kind,_=self.link.sent[-1]
        self.control.receive(Frame(1,Kind.RESULT,sequence=len(self.link.sent),
            payload=struct.pack('<BBHI',kind,code,0,len(self.link.sent))))
    def state(self,phase,active):
        self.control.receive(Frame(1,Kind.REACTION_STATUS,
            payload=STATUS.pack(phase,2,active,0,1488,1500,0,1)))
    def test_configuration_ack_precedes_start_and_completion_is_reported(self):
        self.control.request(self.request)
        self.assertEqual(self.link.sent,[(Kind.REACTION_CONFIGURE,self.request[1:])])
        self.result();self.assertEqual(self.link.sent[-1],(Kind.REACTION,b'\2'))
        self.result();self.state(2,True);self.state(5,True);self.state(1,False)
        self.assertFalse(self.control.running);self.assertEqual(self.events[-1],'END')
    def test_cancelled_configuration_never_starts_on_late_ack(self):
        self.control.request(self.request);self.control.cancel();self.result()
        self.assertFalse(any(k==Kind.REACTION for k,p in self.link.sent))
    def test_rejected_configuration_does_not_start(self):
        self.control.request(self.request);self.result(1)
        self.assertEqual(self.events[-1],'ERROR,mcu_rejected')
        self.assertEqual(len(self.link.sent),1)
    def test_timeout_stops_without_retry(self):
        with patch('mcu_v2.reaction_gateway.time.monotonic',return_value=0):self.control.request(self.request)
        with patch('mcu_v2.reaction_gateway.time.monotonic',return_value=3):self.control.tick();self.control.tick()
        self.assertEqual(self.link.sent[-1],(Kind.STOP,b''));self.assertEqual(len(self.link.sent),2)
    def test_duplicate_while_pending_is_rejected(self):
        self.control.request(self.request);self.control.request(self.request)
        self.assertEqual(len(self.link.sent),1);self.assertEqual(self.events[-1],'ERROR,busy')
    def test_stopping_early_is_interrupted(self):
        self.control.request(self.request);self.result();self.result()
        self.state(2,True);self.state(1,False)
        self.assertEqual(self.events[-1],'INTERRUPTED')
    def test_gateway_stop_cancels_queued_start_but_start_after_stop_is_delivered(self):
        run=GATEWAY_HEADER.pack(0x4C4E5247,1,10,41)+self.request
        stop=GATEWAY_HEADER.pack(0x4C4E5247,1,8,17)+struct.pack('<Bdd',3,0,0)
        for packets,expected in [([run,stop],None),([stop,run],self.request)]:
            g=Gateway('unused');g.socket=Mock()
            g.socket.recv.side_effect=[*packets,BlockingIOError()]
            self.assertEqual(g.latest(),(0.,0.));self.assertEqual(g.reaction_request,expected)

if __name__=='__main__':unittest.main()
