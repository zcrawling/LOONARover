import math
import struct
import unittest
from unittest.mock import patch

from cli.xbox_control import (Controls, TerminalInput, Output, stick,
                             LX, LY, LT, RX, RY, RT)
from backend.real_app import GroundLinkConnection, RealState, HEADER


def axes(**values):
    result = {axis: 0.0 for axis in (LX, LY, LT, RX, RY, RT)}
    for name, value in values.items():
        result[globals()[name]] = value
    return result


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.control = Controls(axes())

    def arm(self):
        self.control.focus(True)
        self.assertEqual(self.control.update(axes(RT=1)), ['MANUAL'])
        self.control.update(axes())

    def test_center_deadzone_minimum_and_endpoints(self):
        self.assertEqual(stick(.08, .08), 0)
        self.assertEqual(stick(-.02, .08), 0)
        self.assertAlmostEqual(stick(.08000001, .08), .01, places=6)
        self.assertEqual(stick(1, .08), 1)
        self.assertEqual(stick(-1, .08), -1)
        self.assertGreater(stick(.75, .08), stick(.25, .08))

    def test_a_separates_translation_and_turning(self):
        self.arm()
        self.control.update(axes(LY=-1, LX=1, RY=1))
        self.assertEqual(self.control.motion(), (1, 0))
        self.control.update(axes(LY=1))
        self.assertEqual(self.control.motion(), (-1, 0))
        self.control.update(axes(LY=-1, RX=-1))
        self.assertEqual(self.control.motion(), (0, 1))
        self.control.update(axes(RX=1))
        self.assertEqual(self.control.motion(), (0, -1))
        self.control.update(axes())
        self.assertEqual(self.control.motion(), (0, 0))

    def test_b_combines_left_axes_and_ignores_right(self):
        self.arm()
        self.control.update(axes(LT=1))
        self.assertEqual(self.control.mode, 'B')
        self.control.update(axes(LY=-1, LX=-1, RX=1, RY=1))
        self.assertEqual(self.control.motion(), (1, 1))
        self.control.update(axes(LY=1, LX=1))
        self.assertEqual(self.control.motion(), (-1, -1))
        self.control.update(axes(LX=1, RX=1))
        self.assertEqual(self.control.motion(), (0, 0))

    def test_trigger_edges_and_hysteresis(self):
        self.control.focus(True)
        for value in (.66, 1, .5, .7):
            self.control.update(axes(LT=value))
            self.assertEqual(self.control.mode, 'B')
        self.control.update(axes(LT=.2))
        self.control.update(axes(LT=.7))
        self.assertEqual(self.control.mode, 'A')
        self.assertEqual(self.control.update(axes(RT=1)), ['MANUAL'])
        self.assertEqual(self.control.update(axes(RT=1)), [])
        self.control.update(axes())
        self.assertEqual(self.control.update(axes(RT=1)), ['STOP'])

    def test_unfocused_input_and_focus_return_do_not_arm(self):
        self.control.update(axes(RT=1, LT=1, LY=-1))
        self.assertFalse(self.control.manual)
        self.assertEqual(self.control.mode, 'A')
        self.control.focus(True)
        self.control.update(axes(RT=1, LT=1, LY=-1))
        self.assertFalse(self.control.manual)
        self.control.update(axes())
        self.control.update(axes(RT=1))
        self.assertTrue(self.control.focus(False))
        self.control.focus(True)
        self.assertFalse(self.control.manual)
        self.assertEqual(self.control.motion(), (0, 0))

    def test_initial_held_trigger_is_not_a_press(self):
        control = Controls(axes(RT=1))
        control.focus(True)
        self.assertEqual(control.update(axes(RT=1)), [])
        self.assertFalse(control.manual)

    def test_partial_focus_sequences_and_keyboard_is_not_arm(self):
        parser = TerminalInput()
        self.assertEqual(parser.feed(b'\r\n\x1b['), [])
        self.assertEqual(parser.feed(b'I\x1b'), ['in'])
        self.assertEqual(parser.feed(b'[O\x1b[Iq'), ['out', 'in', 'quit'])

    def test_uncertain_manual_still_attempts_stop(self):
        output = Output()
        with patch('cli.xbox_control.request', side_effect=[TimeoutError(), {'ok': True}]) as send:
            with self.assertRaises(TimeoutError):
                output.send('MANUAL', (1, .2))
            output.stop()
            self.assertEqual(send.call_args.args[0]['command'], 'STOP')
            self.assertFalse(output.active)

    def test_dry_run_never_uses_backend(self):
        with patch('cli.xbox_control.request', side_effect=AssertionError('network')):
            output = Output(True)
            output.send('MANUAL', (1, 1))
            output.stop()


class VectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_combined_vector_and_existing_keyboard(self):
        state = RealState('local-test')
        state.connection = 'CONNECTED'
        connection = GroundLinkConnection('local-test', 7443, state)
        class Writer:
            def __init__(self): self.frames = []
            def write(self, frame): self.frames.append(frame)
            async def drain(self): pass
        writer = Writer()
        connection.writer = writer
        for v, w in ((1, -1), (-.01, .25), (0, 0)):
            self.assertTrue((await connection.command('MANUAL', linear_mps=v, angular_radps=w))['ok'])
            self.assertEqual(HEADER.unpack_from(writer.frames[-1])[2], 2)
            self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (v, w))
        self.assertTrue((await connection.command('MANUAL'))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (0, 0))
        self.assertTrue((await connection.command('FORWARD'))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (.1, 0))
        count = len(writer.frames)
        for v, w in ((None, 0), (0, None), (True, 0), ('1', 0), (1.1, 0),
                     (math.nan, 0), (0, math.inf)):
            self.assertFalse((await connection.command('MANUAL', linear_mps=v, angular_radps=w))['ok'])
        self.assertFalse((await connection.command('STOP', linear_mps=0, angular_radps=0))['ok'])
        self.assertEqual(len(writer.frames), count)


if __name__ == '__main__':
    unittest.main()
