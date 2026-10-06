"""Command profile only; distance is nominal, never a measured stop target."""
import math

def cruise_duration(speed, ramp, cruise, decel, stop, distance=None):
    if not all(math.isfinite(x) and x > 0 for x in (speed,ramp,decel,stop)):
        raise ValueError('speed/ramp/decel/stop must be finite and positive')
    if distance is not None:
        if not math.isfinite(distance) or distance <= 0: raise ValueError('distance must be positive')
        cruise=distance/speed-(ramp+decel)/2
    if not math.isfinite(cruise) or cruise < 0:
        raise ValueError('distance is shorter than ramp+deceleration distance; reduce speed or ramp durations')
    return cruise

def velocity(t, speed, ramp, cruise, decel):
    if t < ramp: return 'ACCEL',speed*max(t,0)/ramp
    if t < ramp+cruise: return 'CRUISE',speed
    if t < ramp+cruise+decel: return 'DECEL',speed*(1-(t-ramp-cruise)/decel)
    return 'STOP',0.
