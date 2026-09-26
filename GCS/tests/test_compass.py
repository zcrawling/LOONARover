import math
import struct
import unittest
from unittest.mock import patch

from backend.real_app import GroundLinkConnection, RealState
from cli.compass import Heading, border_positions


def snapshot(yaw):
    return {'connection': 'CONNECTED', 'imu_attitude': {
        'rpy_rad': [0, 0, yaw], 'age_s': 0, 'reference': 'gyro_relative'}}


class CompassTests(unittest.TestCase):
    def test_cardinals_start_at_edges_and_left_turn_moves_north_right(self):
        box = (48, 48, 1008, 588)
        positions = border_positions(0, box)
        self.assertEqual(positions['N'], (528, 24))
        self.assertAlmostEqual(positions['E'][0], 1032)
        positions = border_positions(math.pi/2, box)
        self.assertAlmostEqual(positions['N'][0], 1032)
        self.assertAlmostEqual(positions['N'][1], 318)

    def test_labels_stay_outside_video_for_every_heading(self):
        for degrees in range(-360, 361):
            for x, y in border_positions(math.radians(degrees), (48, 48, 1008, 588)).values():
                self.assertTrue(x <= 24.001 or x >= 1031.999 or y <= 24.001 or y >= 611.999)

    def test_reference_wrap_disconnect_and_reset(self):
        heading = Heading()
        self.assertEqual(heading.update(snapshot(math.radians(179))), 0)
        self.assertAlmostEqual(heading.update(snapshot(math.radians(-179))), math.radians(2))
        self.assertIsNone(heading.update({'connection': 'RECONNECTING'}))
        self.assertAlmostEqual(heading.update(snapshot(math.radians(-178))), math.radians(3))
        self.assertIsNone(heading.update({'connection': 'CONNECTED', 'imu_attitude': None}))
        self.assertEqual(heading.update(snapshot(1.2)), 0)

    def test_magnetic_or_stale_values_do_not_claim_a_gyro_heading(self):
        heading = Heading()
        state = snapshot(0)
        state['imu_attitude']['reference'] = 'unspecified'
        self.assertIsNone(heading.update(state))
        state['imu_attitude']['reference'] = 'gyro_relative'
        state['imu_attitude']['age_s'] = 0.7
        self.assertIsNone(heading.update(state))

    def test_wire_decode_state_and_freshness(self):
        state = RealState('test')
        state.connection = 'CONNECTED'
        connection = GroundLinkConnection('unused', 0, state)
        with patch('time.monotonic', return_value=10):
            connection.handle(0x8003, struct.pack('<QI10d', 123, 16 | 32, *([0]*7), 0.1, 0.2, 0.3))
        with patch('time.monotonic', return_value=10.2):
            attitude = state.snapshot()['imu_attitude']
        self.assertEqual(attitude['rpy_rad'], [0.1, 0.2, 0.3])
        self.assertEqual(attitude['reference'], 'gyro_relative')
        self.assertAlmostEqual(attitude['age_s'], 0.2)
        connection.handle(0x8003, struct.pack('<QI10d', 124, 0, *([0]*10)))
        self.assertIsNone(state.snapshot()['imu_attitude'])


if __name__ == '__main__':
    unittest.main()
