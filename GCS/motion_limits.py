"""LOONAR command envelope: 0.4 m/s wheels, 0.21 m track."""
import math

MAX_LINEAR = 0.4
MAX_ANGULAR = 3.8  # Rounded down from 2 * 0.4 / 0.21.
TRACK_M = 0.21


def normalize_motion(linear, angular):
    if not math.isfinite(linear) or not math.isfinite(angular):
        raise ValueError('finite speeds required')
    linear = max(-MAX_LINEAR, min(MAX_LINEAR, linear))
    angular = max(-MAX_ANGULAR, min(MAX_ANGULAR, angular))
    peak = abs(linear) + abs(angular) * TRACK_M / 2
    scale = min(1.0, MAX_LINEAR / peak) if peak else 1.0
    return linear * scale, angular * scale
