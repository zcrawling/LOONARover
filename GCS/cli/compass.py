"""Relative heading and compass border geometry, without GUI dependencies."""
import math


def border_positions(yaw, box, margin=24):
    """Intersect each horizontal cardinal ray with the outside border.

    Positive yaw is a left turn. Thus the initial N moves to screen-right.
    This is a plan-view compass around the picture, not a camera projection.
    """
    left, top, right, bottom = box
    cx, cy = (left+right)/2, (top+bottom)/2
    half_w, half_h = (right-left)/2+margin, (bottom-top)/2+margin
    result = {}
    for name, bearing in zip('NESW', (0, math.pi/2, math.pi, 3*math.pi/2)):
        angle = bearing + yaw
        dx, dy = math.sin(angle), -math.cos(angle)
        scale = min(half_w/max(abs(dx), 1e-12), half_h/max(abs(dy), 1e-12))
        result[name] = (cx+scale*dx, cy+scale*dy)
    return result


class Heading:
    def __init__(self):
        self.reference = None

    def update(self, snapshot):
        attitude = snapshot.get('imu_attitude')
        if snapshot.get('connection') != 'CONNECTED':
            return None  # Network loss does not change the reference on the Pi.
        if attitude is None:
            self.reference = None  # Pi reports invalid during gyro reinitialization.
            return None
        if attitude.get('reference') != 'gyro_relative' or attitude.get('age_s', 999) > 0.5:
            return None
        rpy = attitude.get('rpy_rad', [])
        if len(rpy) != 3 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in rpy):
            return None
        yaw = rpy[2]
        if self.reference is None:
            self.reference = yaw
        return math.atan2(math.sin(yaw-self.reference), math.cos(yaw-self.reference))


