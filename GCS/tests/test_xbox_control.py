import math
import struct
import unittest
from unittest.mock import patch

from cli.xbox_control import (Controls, TerminalInput, Output, stick,
                             XboxDevice, EVENT, EV_KEY, EV_SYN, SYN_REPORT,
                             AXES, LX, LY, LT, RX, RY, RT, LB, RB, X, Y, A, B)
from motion_limits import TRACK_M
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

    def assert_motion_almost_equal(self, actual, expected):
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target)

    def test_center_deadzone_minimum_and_endpoints(self):
        self.assertEqual(stick(.08, .08), 0)
        self.assertEqual(stick(-.02, .08), 0)
        self.assertAlmostEqual(stick(.08000001, .08), .01, places=6)
        self.assertEqual(stick(1, .08), 1)
        self.assertEqual(stick(1, .08, .4), .4)
        self.assertAlmostEqual(stick(.08000001, .08, .4), .01, places=6)
        self.assertAlmostEqual(stick(.54, .08, .4), .205)
        self.assertEqual(stick(-1, .08), -1)
        self.assertGreater(stick(.75, .08), stick(.25, .08))

    def test_a_separates_translation_and_turning(self):
        self.arm()
        self.control.update(axes(LY=-1, LX=1, RY=1))
        self.assertEqual(self.control.motion(), (.4, 0))
        self.control.update(axes(LY=1))
        self.assertEqual(self.control.motion(), (-.4, 0))
        self.control.update(axes(LY=-1, RX=-1))
        self.assertEqual(self.control.motion(), (0, 3.8))
        self.control.update(axes(RX=1))
        self.assertEqual(self.control.motion(), (0, -3.8))
        self.control.update(axes())
        self.assertEqual(self.control.motion(), (0, 0))

    def test_b_combines_left_axes_and_ignores_right_horizontal(self):
        self.arm()
        self.control.update(axes(LT=1))
        self.assertEqual(self.control.mode, 'B')
        self.control.update(axes(LY=-1, LX=-1, RX=1))
        self.assertAlmostEqual(self.control.motion()[0], .4 * .4 / .799)
        self.assertAlmostEqual(self.control.motion()[1], 3.8 * .4 / .799)
        self.control.update(axes(LY=1, LX=1))
        self.assertAlmostEqual(self.control.motion()[0], -.4 * .4 / .799)
        self.assertAlmostEqual(self.control.motion()[1], -3.8 * .4 / .799)
        self.control.update(axes(LX=1, RX=1))
        self.assertEqual(self.control.motion(), (0, 0))

    def test_b_wave_wheel_speeds_forward_reverse_and_limit(self):
        self.arm()
        self.control.update(axes(LT=1))
        for k_steps in (0, 5, 10):
            self.control.k_steps = k_steps
            for ry in (-.4, .4, -1, 1):
                self.control.update(axes())
                # Opposing left stick and right horizontal input must be ignored.
                self.control.update(axes(RY=ry, LY=-ry, LX=1, RX=-1))
                x = -stick(ry, .08, .4)
                self.assert_motion_almost_equal(self.control.motion(100), (x, 0))
                for elapsed, sine in ((.25, 1), (.5, 0), (.75, -1), (1, 0)):
                    v, w = self.control.motion(100 + elapsed)
                    left, right = v - w * TRACK_M / 2, v + w * TRACK_M / 2
                    expected_l = x + self.control.k * x * sine
                    expected_r = x - self.control.k * x * sine
                    scale = max(1, abs(expected_l) / .4, abs(expected_r) / .4)
                    self.assertAlmostEqual(left, expected_l / scale)
                    self.assertAlmostEqual(right, expected_r / scale)
                    self.assertLessEqual(max(abs(left), abs(right)), .4 + 1e-12)

    def test_b_wave_resets_on_release_stop_mode_change_and_focus_loss(self):
        self.arm()
        self.control.update(axes(LT=1))
        self.control.update(axes(RY=-.4))
        x = -stick(-.4, .08, .4)
        self.control.motion(10)
        self.assertLess(self.control.motion(10.25)[1], 0)
        self.control.update(axes(RY=.04, LY=-1))
        self.assertEqual(self.control.motion(11), (.4, 0))
        self.control.update(axes(RY=-.4))
        self.assert_motion_almost_equal(self.control.motion(12), (x, 0))
        self.control.update(axes(RY=-.4, RT=1))
        self.assertEqual(self.control.motion(13), (0, 0))
        self.control.update(axes(RY=-.4))
        self.control.update(axes(RY=-.4, RT=1))
        self.assert_motion_almost_equal(self.control.motion(14), (x, 0))
        self.control.update(axes(RY=-.4, LT=1))
        self.assertEqual(self.control.motion(15), (0, 0))  # A ignores RY.
        self.control.update(axes(RY=-.4))
        self.control.update(axes(RY=-.4, LT=1))
        self.assert_motion_almost_equal(self.control.motion(16), (x, 0))
        self.control.focus(False)
        self.assertEqual(self.control.motion(17), (0, 0))
        self.control.focus(True)
        self.control.update(axes(RY=-.4, RT=1))
        self.assert_motion_almost_equal(self.control.motion(18), (x, 0))

    def test_phase_wheel_speeds_and_common_scaling(self):
        self.arm()
        self.control.update(axes(LT=1))
        # Expected right sine at t=0 and t=1/4 second for each phase.
        for phase, right_sines in ((0, (0, 1)), (90, (1, 0)),
                                   (180, (0, -1)), (270, (-1, 0)), (360, (0, 1))):
            self.control.phase_deg = phase
            for ry in (-.4, .4, -1, 1):
                self.control.update(axes())
                self.control.update(axes(RY=ry))
                x = -stick(ry, .08, .4)
                for elapsed, left_sine, right_sine in ((0, 0, right_sines[0]),
                                                       (.25, 1, right_sines[1])):
                    v, w = self.control.motion(100 + elapsed)
                    left, right = v - w * TRACK_M / 2, v + w * TRACK_M / 2
                    expected = [x * (1 + .5 * left_sine), x * (1 + .5 * right_sine)]
                    scale = max(1, *(abs(speed) / .4 for speed in expected))
                    self.assert_motion_almost_equal((left, right), [speed / scale for speed in expected])
                    self.assertLessEqual(max(abs(left), abs(right)), .4 + 1e-12)

    def test_phase_buttons_edges_limits_focus_and_persistence(self):
        self.assertEqual(self.control.phase_deg, 180)
        self.control.update(axes(Y=1))
        self.control.focus(True)
        self.control.update(axes(Y=1))
        self.assertEqual(self.control.phase_deg, 180)
        self.control.update(axes())
        for _ in range(3):
            self.control.update(axes(Y=1))
        self.assertEqual(self.control.phase_deg, 190)
        self.control.update(axes())
        self.control.update(axes(X=1))
        self.assertEqual(self.control.phase_deg, 180)
        for button, limit in ((X, 0), (Y, 360)):
            for _ in range(40):
                self.control.update(axes())
                self.control.update({**axes(), button: 1})
            self.assertEqual(self.control.phase_deg, limit)
        self.control.focus(False)
        self.control.focus(True)
        self.control.update(axes(LT=1, RT=1))
        self.assertEqual(self.control.phase_deg, 360)
        self.assertEqual(self.control.k, .5)
        held = Controls(axes(X=1, Y=1))
        held.focus(True)
        held.update(axes(X=1, Y=1))
        self.assertEqual(held.phase_deg, 180)

    def test_phase_change_keeps_wave_time(self):
        self.arm()
        self.control.update(axes(LT=1))
        self.control.update(axes(RY=-.4))
        self.control.motion(10)
        self.control.update(axes(RY=-.4, Y=1))
        self.assertEqual(self.control.wave_start, 10)
        self.assertEqual(self.control.phase_deg, 190)
        v, w = self.control.motion(10.25)
        x = -stick(-.4, .08, .4)
        self.assertAlmostEqual(v - w * TRACK_M / 2, 1.5 * x)
        self.assertAlmostEqual(v + w * TRACK_M / 2, x * (1 + .5 * math.sin(math.radians(280))))

    def test_frequency_periods_and_zero_with_phase_offset(self):
        self.arm()
        self.control.update(axes(LT=1))
        for steps in (1, 5, 10, 20):
            self.control.frequency_steps = steps
            self.control.update(axes())
            self.control.update(axes(RY=-.4))
            x = -stick(-.4, .08, .4)
            self.control.motion(100)
            for cycles, expected in ((.25, (1.5*x, .5*x)), (.75, (.5*x, 1.5*x)), (1, (x, x))):
                v, w = self.control.motion(100 + cycles / self.control.f)
                self.assert_motion_almost_equal((v - w*TRACK_M/2, v + w*TRACK_M/2), expected)
        self.control.frequency_steps = 0
        for phase, right_factor in ((0, 1), (90, 1.5), (180, 1), (270, .5), (360, 1)):
            self.control.phase_deg = phase
            for now in (101, 200, 1000):
                v, w = self.control.motion(now)
                self.assert_motion_almost_equal((v - w*TRACK_M/2, v + w*TRACK_M/2), (x, right_factor*x))

    def test_frequency_buttons_edges_limits_focus_and_persistence(self):
        self.assertEqual(self.control.f, 1)
        self.control.update(axes(B=1))
        self.control.focus(True)
        self.control.update(axes(B=1))
        self.assertEqual(self.control.f, 1)
        self.control.update(axes())
        for _ in range(3):
            self.control.update(axes(A=1))
        self.assertEqual(self.control.f, .9)
        self.control.update(axes())
        self.control.update(axes(B=1))
        self.assertEqual(self.control.f, 1)
        for button, limit in ((A, 0), (B, 2)):
            for _ in range(25):
                self.control.update(axes())
                self.control.update({**axes(), button: 1})
            self.assertEqual(self.control.f, limit)
        self.control.update(axes())
        self.control.update(axes(A=1, B=1))
        self.assertEqual(self.control.f, 2)
        self.assertEqual(self.control.mode, 'A')
        self.assertFalse(self.control.manual)
        self.assertEqual((self.control.k, self.control.phase_deg), (.5, 180))
        self.control.focus(False)
        self.control.focus(True)
        self.control.update(axes(LT=1, RT=1))
        self.assertEqual(self.control.f, 2)
        held = Controls(axes(A=1, B=1))
        held.focus(True)
        held.update(axes(A=1, B=1))
        self.assertEqual(held.f, 1)

    def test_frequency_change_applies_to_existing_elapsed_time(self):
        self.arm()
        self.control.update(axes(LT=1))
        self.control.update(axes(RY=-.4))
        self.control.motion(10)
        self.control.update(axes(RY=-.4, B=1))
        self.assertEqual(self.control.wave_start, 10)
        self.assertEqual(self.control.f, 1.1)
        v, w = self.control.motion(12.5)
        x = -stick(-.4, .08, .4)
        # 1.1 * 2.5 = 2.75 cycles, hence sin=-1.
        self.assert_motion_almost_equal((v - w*TRACK_M/2, v + w*TRACK_M/2), (.5*x, 1.5*x))

    def test_bumpers_once_per_press_bounds_and_focus(self):
        self.assertEqual(self.control.k, .5)
        self.control.update(axes(RB=1))
        self.control.focus(True)
        self.control.update(axes(RB=1))  # Held while returning focus: no change.
        self.assertEqual(self.control.k, .5)
        self.control.update(axes())
        for _ in range(3):
            self.control.update(axes(RB=1))
        self.assertEqual(self.control.k, .6)
        self.control.update(axes())
        self.control.update(axes(LB=1))
        self.assertEqual(self.control.k, .5)
        for button, limit in ((RB, 1), (LB, 0)):
            for _ in range(20):
                self.control.update(axes())
                self.control.update({**axes(), button: 1})
            self.assertEqual(self.control.k, limit)
        held = Controls(axes(LB=1, RB=1))
        held.focus(True)
        held.update(axes(LB=1, RB=1))
        self.assertEqual(held.k, .5)

    def test_evdev_bumper_press_repeat_release(self):
        device = XboxDevice.__new__(XboxDevice)
        device.fd = -1
        device.buffer = b''
        device.values = {a: 0 for a in AXES}
        device.info = {a: (0, -32768, 32767, 0, 0, 0) for a in AXES}
        self.control.focus(True)
        for value, expected in ((1, .6), (2, .6), (0, .6), (1, .7)):
            packet = EVENT.pack(0, 0, EV_KEY, RB, value) + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0)
            with patch('cli.xbox_control.os.read', return_value=packet):
                for report in device.reports():
                    self.control.update(report)
            self.assertEqual(self.control.k, expected)
        for button, value, expected in ((X, 1, 170), (X, 2, 170), (X, 0, 170),
                                        (Y, 1, 180), (Y, 0, 180), (Y, 1, 190)):
            packet = EVENT.pack(0, 0, EV_KEY, button, value) + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0)
            with patch('cli.xbox_control.os.read', return_value=packet):
                for report in device.reports():
                    self.control.update(report)
            self.assertEqual(self.control.phase_deg, expected)
        for button, value, expected in ((A, 1, .9), (A, 2, .9), (A, 0, .9),
                                        (B, 1, 1), (B, 0, 1), (B, 1, 1.1)):
            packet = EVENT.pack(0, 0, EV_KEY, button, value) + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0)
            with patch('cli.xbox_control.os.read', return_value=packet):
                for report in device.reports():
                    self.control.update(report)
            self.assertEqual(self.control.f, expected)

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
        for v, w in ((.2, -1), (-.01, .25), (0, 0)):
            self.assertTrue((await connection.command('MANUAL', linear_mps=v, angular_radps=w))['ok'])
            self.assertEqual(HEADER.unpack_from(writer.frames[-1])[2], 2)
            self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (v, w))
        self.assertTrue((await connection.command('MANUAL'))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (0, 0))
        self.assertTrue((await connection.command('FORWARD'))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (.1, 0))
        for v, w, expected in ((2, 0, (.4, 0)), (-2, 0, (-.4, 0)),
                               (0, 10, (0, 3.8)), (0, -10, (0, -3.8))):
            self.assertTrue((await connection.command('MANUAL', linear_mps=v, angular_radps=w))['ok'])
            self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), expected)
        self.assertTrue((await connection.command('FORWARD', linear_speed_mps=2))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (.4, 0))
        self.assertTrue((await connection.command('LEFT', angular_speed_radps=10))['ok'])
        self.assertEqual(struct.unpack('<dd', writer.frames[-1][16:]), (0, 3.8))
        count = len(writer.frames)
        for v, w in ((None, 0), (0, None), (True, 0), ('1', 0),
                     (math.nan, 0), (0, math.inf)):
            self.assertFalse((await connection.command('MANUAL', linear_mps=v, angular_radps=w))['ok'])
        self.assertFalse((await connection.command('STOP', linear_mps=0, angular_radps=0))['ok'])
        self.assertEqual(len(writer.frames), count)


if __name__ == '__main__':
    unittest.main()
