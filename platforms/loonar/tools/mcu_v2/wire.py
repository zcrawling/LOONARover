"""LNR2 framing, shared by the backend and device diagnostics."""

from dataclasses import dataclass
from enum import IntEnum
import struct

HEADER = struct.Struct("<4sBBBBIIIQHH")
MAX_PAYLOAD = 192


class Kind(IntEnum):
    HELLO_REQUEST = 1
    HELLO = 2
    SESSION = 3
    HEALTH_REQUEST = 4
    HEALTH = 5
    MOTION = 6
    STOP = 7
    CONFIGURE = 8
    ACK = 9
    RESULT = 10
    TIME_REQUEST = 11
    TIME = 12
    IMU = 32
    MOTOR = 33


def crc32c(data):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


@dataclass(frozen=True)
class Frame:
    role: int
    kind: int
    boot: int = 0
    session: int = 0
    sequence: int = 0
    stamp_us: int = 0
    payload: bytes = b""

    def encode(self):
        if self.role not in (1, 2) or len(self.payload) > MAX_PAYLOAD:
            raise ValueError("invalid role or oversized MCU frame")
        raw = (
            HEADER.pack(
                b"LNR2",
                2,
                self.role,
                self.kind,
                0,
                self.boot,
                self.session,
                self.sequence,
                self.stamp_us,
                len(self.payload),
                0,
            )
            + self.payload
        )
        return raw + struct.pack("<I", crc32c(raw))


class Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 4:
            if self.buffer[:4] != b"LNR2":
                del self.buffer[0]
                self.errors += 1
                continue
            if len(self.buffer) < HEADER.size:
                break
            _, version, role, kind, flags, boot, session, seq, stamp, size, reserved = (
                HEADER.unpack_from(self.buffer)
            )
            if (
                version != 2
                or role not in (1, 2)
                or flags
                or reserved
                or size > MAX_PAYLOAD
            ):
                del self.buffer[0]
                self.errors += 1
                continue
            total = HEADER.size + size + 4
            if len(self.buffer) < total:
                break
            raw = bytes(self.buffer[:total])
            if crc32c(raw[:-4]) != struct.unpack_from("<I", raw, total - 4)[0]:
                del self.buffer[0]
                self.errors += 1
                continue
            frames.append(
                Frame(role, kind, boot, session, seq, stamp, raw[HEADER.size : -4])
            )
            del self.buffer[:total]
        return frames

    def expire(self):
        if self.buffer:
            self.errors += 1
            self.buffer.clear()
