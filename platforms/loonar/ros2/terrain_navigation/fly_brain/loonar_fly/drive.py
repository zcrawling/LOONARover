"""Bounded neural command gate and the existing gateway's local mode channel."""
import math
import socket
import struct


class ModeChannel:
    """Own cfs.sock only in the standalone runner, where cFS is NOT started."""
    def __init__(self, path):
        self.path = str(path)
        self.socket = None
        self.auto = False

    def send(self, kind):
        self.socket.sendall(struct.pack("<IHHI", 0x4C4E5247, 1, kind, 0))

    def connect(self):
        if self.socket is not None:
            # Drain status to keep the daemon's nonblocking send queue free.
            try:
                for _ in range(64):
                    if not self.socket.recv(256):
                        raise ConnectionError("gateway closed mode channel")
            except BlockingIOError:
                return
            except OSError:
                self.close()
                raise
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        sock.settimeout(.005)
        try:
            sock.connect(self.path)
            self.socket = sock
            self.send(1)
            self.send(3)  # always begin with STOP; never replay AUTO on reconnect
            self.socket.setblocking(False)
        except OSError:
            sock.close()
            self.socket = None
            raise

    def select_auto(self):
        if not self.auto:
            self.send(4)
            self.auto = True

    def stop(self):
        self.auto = False
        if self.socket is not None:
            try:
                self.send(3)
            except OSError:
                self.close()

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.auto = False


class DriveGate:
    """Require a stable fresh stream, clamp outputs, latch explicit shutdown."""
    def __init__(self, settle_seconds=.5, max_drive_seconds=0, max_speed=.2):
        if not math.isfinite(max_drive_seconds) or max_drive_seconds < 0:
            raise ValueError("invalid drive duration")
        self.settle_seconds = settle_seconds
        self.max_drive_seconds = max_drive_seconds
        if not math.isfinite(max_speed) or not 0 < max_speed <= .2:
            raise ValueError("max_speed must be >0 and <=0.2 m/s")
        self.max_speed = max_speed
        self.last_time = None
        self.last_v = 0.0
        self.clear_since = None
        self.started = None
        self.latched = ""
        self.reason = "waiting for sensors and brain"

    def halt(self, reason):
        self.latched = reason

    def evaluate(self, now, blocked, candidate):
        dt = 0 if self.last_time is None else max(0.0, min(now - self.last_time, .1))
        self.last_time = now
        if self.started is not None and self.max_drive_seconds and now - self.started >= self.max_drive_seconds:
            self.halt("drive duration reached; restart Pi command to rearm")
        self.reason = self.latched or blocked
        if self.reason:
            self.clear_since = None
            self.last_v = 0.0
            return False, 0.0, 0.0
        if self.clear_since is None:
            self.clear_since = now
        if now - self.clear_since < self.settle_seconds:
            self.last_v = 0.0
            self.reason = "waiting for 0.5s continuous clear/fresh inputs"
            return False, 0.0, 0.0
        v, w = candidate["linear_mps"], candidate["angular_rps"]
        if not all(math.isfinite(x) for x in (v, w)):
            self.reason = "invalid neural command"
            self.clear_since = None
            self.last_v = 0.0
            return False, 0.0, 0.0
        v, w = max(0.0, min(self.max_speed, v)), max(-.6, min(.6, w))
        # Only acceleration is limited. Braking and STOP are never ramped.
        v = min(v, self.last_v + .1 * dt)
        self.last_v = v
        if self.started is None and (v != 0 or w != 0):
            self.started = now
        return True, v, w
