"""Persistent initial IMU yaw goal; local measured-obstacle avoidance wins."""
import math


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_from_quaternion(q):
    values = (q.x, q.y, q.z, q.w)
    norm = math.sqrt(sum(v*v for v in values))
    if not all(math.isfinite(v) for v in values) or norm < .5:
        raise ValueError('invalid IMU quaternion')
    x,y,z,w = (v/norm for v in values)
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


class HeadingGoal:
    def __init__(self, target=None):
        if target is not None and not math.isfinite(target):
            raise ValueError("heading target must be finite")
        self.target = target
        self.yaw = None
        self.error = None

    def observe(self, yaw):
        if not math.isfinite(yaw):
            return
        if self.target is None:
            self.target = yaw
        self.yaw = yaw
        self.error = wrap(self.target-yaw)

    def command(self, command, decision):
        result = dict(command)
        if self.error is None or decision.get('mode') in ('turn','no_turn_room','await_scene'):
            return result
        # Restore the original direction after avoidance, including +-pi wrap.
        # Flat-surface steering is a local detour, not a replacement heading.
        correction = max(-.4, min(.4, 1.2*self.error))
        result['angular_rps'] = max(-.4,min(.4, correction + .25*command['angular_rps']))
        if abs(self.error) > math.pi/3:
            result['linear_mps'] = 0.0
        return result

    def status(self):
        return dict(target_rad=self.target, current_rad=self.yaw, error_rad=self.error)
