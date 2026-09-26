import math
import struct
import unittest
from unittest.mock import Mock, patch

from .backend import Gateway, GATEWAY_HEADER
from .gyro_attitude import GyroAttitude
from .wire import Frame, Kind


def sample(seq, seconds, rates, sensor=2, lost=0, boot=1):
    payload = struct.pack('<4BQ5f4x', sensor, 3, seq % 256, lost,
                          round(seconds * 1e6), *rates, 0, 0)
    return Frame(1, Kind.IMU, boot=boot, sequence=seq, stamp_us=round(seconds*1e6), payload=payload)


def initialize(gravity=(0, 0, 9.81)):
    attitude = GyroAttitude()
    attitude.update(sample(1, 0, gravity, sensor=6), 0)
    attitude.update(sample(2, 0, (0, 0, 0)), 0)
    return attitude


class GyroAttitudeTests(unittest.TestCase):
    def test_y_forward_z_up_left_turn_and_no_duplicate_integration(self):
        attitude = initialize()
        for n in range(1, 201):
            frame = sample(n+2, n/200, (0, 0, math.pi/2))
            attitude.update(frame, n/200)
            attitude.update(frame, n/200)
        roll, pitch, yaw = attitude.rpy(1)
        self.assertAlmostEqual(yaw, math.pi/2, places=6)
        self.assertAlmostEqual(roll, 0)
        self.assertAlmostEqual(pitch, 0)
        self.assertIsNone(attitude.rpy(1.3))

    def test_initial_gravity_handles_upside_down_mount(self):
        attitude = initialize((0, 0, -9.81))
        for n in range(1, 201):
            attitude.update(sample(n+2, n/200, (0, 0, -math.pi/2)), n/200)
        self.assertAlmostEqual(attitude.rpy(1)[2], math.pi/2, places=6)

    def test_all_three_sensor_axes_are_integrated(self):
        # Sensor +Y = body roll axis; sensor -X = body pitch axis.
        for rates, index in (((0, 0.4, 0), 0), ((-0.4, 0, 0), 1), ((0, 0, 0.4), 2)):
            attitude = initialize()
            for n in range(1, 201):
                attitude.update(sample(n+2, n/200, rates), n/200)
            values = attitude.rpy(1)
            for axis, value in enumerate(values):
                self.assertAlmostEqual(value, 0.4 if axis == index else 0, places=6)

    def test_gap_and_boot_change_invalidate_reference(self):
        attitude = initialize()
        attitude.update(sample(3, 1, (0, 0, 1), sensor=6), 1)
        attitude.update(sample(4, 1, (0, 0, 1)), 1)
        self.assertIsNone(attitude.rpy(1))
        attitude.update(sample(5, 1.005, (0, 0, 1), boot=2), 1.005)
        self.assertIsNone(attitude.rpy(1.005))

    def test_tilted_three_axis_rotation_is_not_just_integrated_z(self):
        attitude = initialize()
        for n in range(1, 401):
            rates = (0, math.pi/2, 0) if n <= 200 else (-math.pi/2, 0, 0)
            attitude.update(sample(n+2, n/200, rates), n/200)
        roll, pitch, yaw = attitude.rpy(2)
        self.assertAlmostEqual(roll, math.pi/2, places=5)
        self.assertAlmostEqual(pitch, 0, places=5)
        self.assertAlmostEqual(yaw, math.pi/2, places=5)

    def test_gravity_is_required_and_magnetic_orientation_is_ignored(self):
        attitude = GyroAttitude()
        attitude.update(sample(1, 0, (0, 0, 1)), 0)
        attitude.update(sample(2, 0, (0, 0, 1), sensor=5), 0)
        self.assertIsNone(attitude.rpy(0))

    def test_existing_vehicle_packet_carries_relative_attitude(self):
        gateway = Gateway('unused')
        gateway.socket = Mock()
        with patch('time.monotonic', return_value=0):
            gateway.status(sample(1, 0, (0, 0, 9.81), sensor=6), None)
            gateway.status(sample(2, 0, (0, 0, 0)), None)
        for n in range(1, 201):
            with patch('time.monotonic', return_value=n/200):
                gateway.status(sample(n+2, n/200, (0, 0, 0.4)), None)
        with patch('time.monotonic', return_value=1):
            gateway.status(Frame(1, Kind.MOTOR, payload=bytes(64)), None)
        packet = gateway.socket.send.call_args.args[0]
        self.assertEqual(len(packet), GATEWAY_HEADER.size+92)
        values = struct.unpack_from('<QI10d', packet, GATEWAY_HEADER.size)
        self.assertEqual(values[1], 16 | 32)
        self.assertAlmostEqual(values[-1], 0.4, places=6)


if __name__ == '__main__':
    unittest.main()
