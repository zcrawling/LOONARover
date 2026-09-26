"""Display-only relative attitude from calibrated gyro samples; no motion feedback."""
import math
import struct


class GyroAttitude:
    def __init__(self):
        self.gravity = None
        self.forward = self.left = self.up = None
        self.q = (1.0, 0.0, 0.0, 0.0)
        self.boot = self.sequence = self.stamp = self.last_rx = None
        self.invalid_until = 0.0

    def update(self, frame, now):
        p = frame.payload
        if len(p) != 36 or p[0] not in (2, 6):
            return
        rates = struct.unpack_from('<3f', p, 12)
        if not all(math.isfinite(v) for v in rates):
            return
        if p[0] == 6:  # SH2_GRAVITY: accelerometer gravity component points up at rest.
            self.gravity = (rates, frame.boot, now)
            return
        if self.boot == frame.boot and self.sequence is not None and frame.sequence <= self.sequence:
            return  # RAM replay must not be integrated twice or refresh freshness.
        stamp = struct.unpack_from('<Q', p, 4)[0]  # SH-2 sensor timestamp, microseconds.
        dt = None if self.stamp is None else (stamp - self.stamp) / 1e6
        restart = self.boot != frame.boot or dt is None or not 0 < dt <= 0.1 or p[3] != 0
        if restart:
            if not self.gravity or self.gravity[1] != frame.boot or now - self.gravity[2] > 0.2:
                self.last_rx = None
                return
            gravity = self.gravity[0]
            norm = math.sqrt(sum(v*v for v in gravity))
            if norm < 1e-6:
                return
            up = tuple(v/norm for v in gravity)
            # Sensor +Y is camera/rover forward. Project it onto the initial
            # horizontal plane; gravity determines mounting tilt and up/down.
            forward = tuple(v-up[1]*u for v, u in zip((0, 1, 0), up))
            norm = math.sqrt(sum(v*v for v in forward))
            if norm < 1e-6:
                return
            self.up, self.forward = up, tuple(v/norm for v in forward)
            a, b = self.up, self.forward
            self.left = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
            # Unknown rotation across a gap cannot be recovered. Expose an invalid
            # interval so the PC drops its old reference before accepting a new one.
            self.q = (1.0, 0.0, 0.0, 0.0)
            self.invalid_until = now + 0.5
        else:
            wx, wy, wz = (sum(a*b for a, b in zip(axis, rates))
                          for axis in (self.forward, self.left, self.up))
            speed = math.sqrt(wx*wx + wy*wy + wz*wz)
            half = speed * dt / 2
            scale = math.sin(half) / speed if speed else dt / 2
            a, b, c, d = self.q
            w, x, y, z = math.cos(half), wx*scale, wy*scale, wz*scale
            q = (a*w-b*x-c*y-d*z, a*x+b*w+c*z-d*y,
                 a*y-b*z+c*w+d*x, a*z+b*y-c*x+d*w)
            norm = math.sqrt(sum(v*v for v in q))
            self.q = tuple(v / norm for v in q)
        self.boot, self.sequence, self.stamp = frame.boot, frame.sequence, stamp
        self.last_rx = now

    def rpy(self, now):
        if self.last_rx is None or now - self.last_rx > 0.2 or now < self.invalid_until:
            return None
        w, x, y, z = self.q
        return (math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)),
                math.asin(max(-1, min(1, 2*(w*y-z*x)))),
                math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))
