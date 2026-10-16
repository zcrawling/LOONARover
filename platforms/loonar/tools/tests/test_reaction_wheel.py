import sys
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcu_v2.reaction_wheel import Settings, status, run
from mcu_v2.wire import Frame, Kind

class FakeLink:
    def __init__(self, rejected=False):
        self.sent=[]; self.frames=[]; self.seq=0; self.rejected=rejected
    def send(self, kind, payload=b''):
        self.seq+=1; self.sent.append((kind,payload))
        if kind==Kind.HEALTH_REQUEST and not any(k==Kind.REACTION for k,p in self.sent):
            self.frames.append(Frame(1,Kind.REACTION_STATUS,payload=struct.pack('<BBBBHHII',1,0,0,0,1488,1500,0,0)))
        if kind==Kind.REACTION:
            self.frames.append(Frame(1,Kind.RESULT,sequence=self.seq,payload=bytes([13,self.rejected,0,0])+struct.pack('<I',self.seq)))
            for state,esc,servo in [(2,1513,1500),(3,1538,1500),(4,1488,1500),(5,1488,800),(1,1488,1500)]:
                self.frames.append(Frame(1,Kind.REACTION_STATUS,payload=struct.pack('<BBBBHHII',state,0 if state==1 else payload[0],state!=1,0,esc,servo,0,1)))
        return self.seq
    def wait(self,kind,timeout,sequence): return Frame(1,Kind.RESULT,sequence=sequence,payload=bytes([14,0,0,0])+struct.pack('<I',sequence))
    @staticmethod
    def check_result(frame,kind):
        if frame.payload[0]!=kind or frame.payload[1]: raise ValueError('rejected')
    def poll(self):
        frames,self.frames=self.frames,[]
        return frames

class ReactionTests(unittest.TestCase):
    def test_defaults_match_mcu_layout(self):
        self.assertEqual(struct.unpack('<8H6I',Settings().encode()),
            (1488,1500,25,50,25,50,800,2200,5000,10000,10000,10,3000,5000))
    def test_reject_invalid_settings_before_serial_command(self):
        for values in ({'servo_left':799},{'esc_neutral':2000},{'servo_delay_ms':0},
                       {'left_first_ms':0},{'right_second_offset':1000},{'second_ms':True}):
            link=FakeLink()
            with self.subTest(values=values),self.assertRaises(ValueError):
                run(link,'left',Settings(**values))
            self.assertFalse(link.sent)
    def test_direction_and_completion(self):
        for side,value in [('left',1),('right',2)]:
            link=FakeLink()
            with patch('builtins.print'),patch('time.sleep'):
                run(link,side,Settings())
            commands=[p for k,p in link.sent if k==Kind.REACTION]
            self.assertEqual(commands,[bytes([value])])
            self.assertEqual(link.sent[0],(Kind.STOP,b''))
    def test_stop_never_starts_cycle(self):
        link=FakeLink(); run(link,'stop',Settings())
        self.assertEqual(link.sent,[(Kind.STOP,b'')])
    def test_rejection_never_retries(self):
        link=FakeLink(rejected=True)
        with patch('builtins.print'),patch('time.sleep'),self.assertRaises(ValueError):
            run(link,'left',Settings())
        self.assertEqual(sum(k==Kind.REACTION for k,p in link.sent),1)
    def test_status_decode(self):
        self.assertEqual(status(struct.pack('<BBBBHHII',5,2,1,0,1488,2200,250,7))['state'],'SERVO_HOLD')
        with self.assertRaises(ValueError): status(b'bad')

if __name__=='__main__': unittest.main()
