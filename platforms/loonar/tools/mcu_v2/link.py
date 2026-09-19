import secrets
import struct
import time
from .wire import Frame, Kind, Parser


class Link:
    def __init__(self, device, serial_factory=None):
        if serial_factory is None:
            import serial

            serial_factory = serial.Serial
        self.device = device
        self.port = serial_factory(
            device["device"],
            baudrate=2000000,
            timeout=0,
            write_timeout=0.1,
            exclusive=True,
        )
        self.parser = Parser()
        self.sequence = 0
        self.boot = 0
        self.session = 0
        self.last_rx = time.monotonic()
        self.last_health = 0.0
        self.health = None
        self.offset_ns = None
        self.time_rtt_ns = None
        self.pending_times = {}
        try:
            self.send(Kind.HELLO_REQUEST)
            hello = self.wait(Kind.HELLO, 2)
            if len(hello.payload) != 28:
                raise ValueError("invalid HELLO")
            uid, expected, oldest, latest, flags = struct.unpack_from(
                "<QQIII", hello.payload
            )
            if uid != device["uid_int"] or expected != uid or not flags & 1:
                raise ValueError("MCU UID/binding does not match role registry")
            self.boot = hello.boot
            self.oldest = oldest
            self.latest = latest
            self.session = secrets.randbelow(0xFFFFFFFF) + 1
            request = self.send(Kind.SESSION, struct.pack("<Q", uid))
            self.check_result(self.wait(Kind.RESULT, 2, request), Kind.SESSION)
        except BaseException:
            self.port.close()
            raise

    def send(self, kind, payload=b""):
        if self.sequence >= 0xFFFFFFFF:
            raise RuntimeError("renew connection before request sequence wraps")
        self.sequence += 1
        raw = Frame(
            self.device["role_id"],
            kind,
            self.boot,
            self.session,
            self.sequence,
            0,
            payload,
        ).encode()
        if self.port.write(raw) != len(raw):
            raise OSError("partial serial write")
        return self.sequence

    def poll(self):
        now = time.monotonic()
        if now - self.last_rx > 0.05:
            self.parser.expire()
        raw = self.port.read(8192)
        if raw:
            self.last_rx = now
        frames = []
        for f in self.parser.feed(raw):
            if f.role != self.device["role_id"]:
                raise ValueError("wrong MCU role on registered link")
            if self.boot and f.boot != self.boot:
                raise ConnectionError("MCU restarted; new identity handshake required")
            if self.session and f.session != self.session:
                continue
            if f.kind == Kind.HEALTH:
                if (
                    len(f.payload) != 88
                    or struct.unpack_from("<Q", f.payload)[0] != self.device["uid_int"]
                ):
                    raise ValueError("invalid health identity")
                self.last_health = now
                self.health = f
                self.oldest = struct.unpack_from("<I", f.payload, 84)[0]
            elif f.kind == Kind.TIME and len(f.payload) == 16:
                token, mcu_us = struct.unpack("<QQ", f.payload)
                sent = self.pending_times.pop(f.sequence, None)
                end = time.time_ns()
                if sent is not None and token == sent and 0 <= end - sent <= 20_000_000:
                    self.offset_ns = (sent + end) // 2 - mcu_us * 1000
                    self.time_rtt_ns = end - sent
            frames.append(f)
        return frames

    def wait(self, kind, timeout, sequence=None):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for f in self.poll():
                if f.kind == kind and (sequence is None or f.sequence == sequence):
                    return f
            time.sleep(0.002)
        raise TimeoutError(f"MCU reply {kind} timed out")

    @staticmethod
    def check_result(frame, kind):
        if len(frame.payload) != 8 or frame.payload[0] != kind or frame.payload[1] != 0:
            raise ValueError(f"MCU rejected request {kind}")

    def configure(self, payload):
        request = self.send(Kind.CONFIGURE, payload)
        self.check_result(self.wait(Kind.RESULT, 2, request), Kind.CONFIGURE)

    def timesync(self):
        token = time.time_ns()
        self.pending_times.clear()
        sequence = self.send(Kind.TIME_REQUEST, struct.pack("<Q", token))
        self.pending_times[sequence] = token

    def close(self):
        try:
            if self.session:
                self.send(Kind.STOP)
        except (OSError, RuntimeError):
            pass
        finally:
            self.port.close()
