"""Pair gyro and gravity-free acceleration from the same MCU burst only."""
import math

class ImuPair:
    def __init__(self):
        self.stamp = None
        self.values = {}

    def add(self, sensor, stamp, vector):
        if sensor not in (2, 4):
            return None
        if not all(math.isfinite(v) for v in vector):
            return None
        if stamp != self.stamp:
            self.stamp = stamp
            self.values = {}
        self.values[sensor] = tuple(vector)
        if 2 in self.values and 4 in self.values:
            result = (self.values[2], self.values[4])
            self.values = {}  # never republish an old pair
            return result
        return None
