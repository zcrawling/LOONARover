import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loonar_terrain_core.algorithms import (
    Stationarity,
    evaluate,
    command_distance,
    primitive_command,
    fresh,
    collision_guard,
)

P = dict(
    robot_width=0.2,
    robot_length=0.2,
    tail_offset=0.1,
    safety_margin=0.01,
    max_unknown_ratio=0.0,
    min_confidence=0.6,
    max_slope=0.3,
    max_cross_slope=0.2,
    max_roughness=0.02,
    max_step_up=0.04,
    max_step_down=0.04,
    max_drop_depth=0.04,
    w_slope=1.0,
    w_roughness=1.0,
    w_step=1.0,
    w_risk=1.0,
    w_unknown=1.0,
    w_turn=0.3,
    w_heading_change=0.3,
    w_progress=1.0,
    lookahead_distance=0.6,
    min_drive_distance=0.1,
    max_drive_distance=0.25,
    distance_safety_factor=0.6,
    stopping_margin=0.05,
)


def grid():
    cells = [
        NS(
            unknown=False,
            observed=True,
            drop_suspect=False,
            confidence=1.0,
            slope=0.0,
            roughness=0.0,
            step_up=0.0,
            step_down=0.0,
            depression_depth=0.0,
            gradient_x=0.0,
            gradient_y=0.0,
        )
        for _ in range(40 * 30)
    ]
    return NS(
        resolution=0.05, x_min=-0.5, y_min=-0.75, size_x=40, size_y=30, cells=cells
    )


class Tests(unittest.TestCase):
    def test_short_observed_corridor_stops_before_impassable_step(self):
        p = dict(P, robot_length=0.30, tail_offset=0.15, stopping_margin=0.07)
        g = grid()
        g.resolution = 0.025
        g.x_min = -0.25
        g.y_min = -0.375
        for i in range(g.size_x):
            if g.x_min + (i + 0.5) * g.resolution >= 0.35:
                for j in range(g.size_y):
                    g.cells[i * g.size_y + j].step_up = 0.2
        c = evaluate(g, 0, 0, p)
        self.assertLess(c.safe_distance, 0.20)
        self.assertGreaterEqual(command_distance(c.safe_distance, p), 0.10)
        self.assertLessEqual(
            command_distance(c.safe_distance, p) + 0.07, c.safe_distance
        )

    def test_traversable_step_continues_but_high_step_and_drop_stop(self):
        g = grid()
        for c in g.cells:
            c.step_up = 0.03
            c.step_down = 0.03
        self.assertGreater(evaluate(g, 0, 0, P).safe_distance, 0.5)
        for c in g.cells:
            c.step_up = 0.05
        self.assertEqual(evaluate(g, 0, 0, P).safe_distance, 0)
        for c in g.cells:
            c.step_up = 0.03
            c.drop_suspect = True
        self.assertEqual(evaluate(g, 0, 0, P).safe_distance, 0)

    def test_braking_guard_uses_body_gap_speed_and_step_height(self):
        p = dict(
            P,
            robot_length=0.30,
            tail_offset=0.15,
            wheel_radius=0.10,
            wheel_track=0.21,
            sensor_timeout=0.30,
            brake_reaction_time=0.10,
            brake_deceleration=0.20,
            gyro_threshold=0.04,
            collision_half_width=0.20,
            collision_min_height=-0.065,
            collision_max_height=0.60,
            collision_min_points=4,
            max_step_up=0.035,
            stopping_margin=0.07,
        )

        def blocked(x, height, wheel=0.0, yaw=0.0):
            pts = np.tile([x, 0.0, height - p["wheel_radius"]], (6, 1))
            return collision_guard(pts, [wheel, wheel], yaw, p)[0]

        self.assertFalse(blocked(0.18, 0.03))  # low relief: planner decides
        self.assertTrue(blocked(0.18, 0.04))  # only 3 cm from body nose
        self.assertFalse(blocked(0.35, 0.20))  # room to approach, not immediate stop
        self.assertFalse(blocked(0.28, 0.20))
        self.assertFalse(blocked(0.25, 0.20, yaw=0.003))  # stationary IMU noise
        self.assertTrue(blocked(0.28, 0.20, wheel=1.0))  # 0.1 m/s braking
        self.assertTrue(blocked(0.30, 0.20, wheel=2.0))
        self.assertTrue(blocked(0.28, 0.20, yaw=0.5))

    def test_freshness(self):
        self.assertFalse(fresh(2.0, 1.0, 0.3))
        self.assertFalse(fresh(None, 1.0, 0.3))
        self.assertTrue(fresh(0.8, 1.0, 0.3))

    def test_flat_safe_and_conservative(self):
        c = evaluate(grid(), 0, 0, P)
        self.assertTrue(math.isfinite(c.cost))
        self.assertGreater(c.safe_distance, 0.5)
        self.assertLess(command_distance(c.safe_distance, P), c.safe_distance)
        self.assertEqual(command_distance(0.1, P), 0.0)

    def test_unknown_drop_step_confidence(self):
        for field, value in [
            ("unknown", True),
            ("drop_suspect", True),
            ("step_up", 0.1),
            ("step_down", 0.1),
            ("depression_depth", 0.1),
            ("confidence", 0.2),
            ("slope", float("nan")),
        ]:
            g = grid()
            for i in range(12, 40):
                for j in range(30):
                    setattr(g.cells[i * 30 + j], field, value)
            c = evaluate(g, 0, 0, P)
            self.assertFalse(math.isfinite(c.cost), (field, c))

    def test_map_exterior_is_unsafe(self):
        g = grid()
        g.x_min = 0.1
        self.assertFalse(math.isfinite(evaluate(g, 0, 0, P).cost))

    def test_cross_slope_heading_dependent(self):
        g = grid()
        for c in g.cells:
            c.gradient_y = 0.5
        self.assertFalse(math.isfinite(evaluate(g, 0, 0, P).cost))

    def test_stationary_gravity_and_motion(self):
        p = dict(
            minimum_duration=0.5,
            settling_min_time=0.4,
            wheel_velocity_threshold=0.03,
            gyro_threshold=0.04,
            gyro_std_threshold=0.01,
            accel_std_threshold=0.1,
        )
        s = Stationarity()
        for k in range(60):
            state, conf = s.update(k * 0.02, [0, 0, 0], [0, 0, 9.81], [0, 0], False, p)
        self.assertEqual(state, 2)
        self.assertEqual(
            s.update(1.2, [0, 0, 0], [0, 0, 9.81], [0.2, 0], False, p)[0], 0
        )
        self.assertNotEqual(
            s.update(0.1, [0, 0, 0], [0, 0, 9.81], [0, 0], False, p)[0], 2
        )

    def test_motion_heading_and_completion(self):
        p = dict(
            distance_tolerance=0.005,
            straight_normal_speed=0.1,
            distance_kp=1.0,
            straight_yaw_kp=1.0,
            straight_yaw_kd=0.1,
            max_heading_correction=0.2,
            yaw_tolerance=0.02,
            settle_gyro_threshold=0.03,
            rotate_speed=0.2,
            rotate_kp=1.0,
        )
        v, w, done = primitive_command(1, 0.2, 0.1, 0.1, 0.1, 0.1, p)
        self.assertLess(w, 0)
        self.assertFalse(done)
        self.assertTrue(primitive_command(1, 0.2, 0.1, 0.21, 0, 0, p)[2])
        self.assertFalse(primitive_command(2, 0.5, 0.2, 0, 0.5, 0.2, p)[2])
        self.assertTrue(primitive_command(2, 0.5, 0.2, 0, 0.5, 0, p)[2])


if __name__ == "__main__":
    unittest.main()
