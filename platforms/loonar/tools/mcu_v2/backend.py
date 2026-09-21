"""One serial owner per role. Gateway motion is forwarded once, never refreshed."""

import argparse
import fcntl
import json
import logging
import math
from pathlib import Path
import signal
import socket
import struct
import time
from .config import load, driver_packet, geometry, wheel_command
from .buffer import ReceiveBuffer
from .link import Link
from .wire import Kind

HEALTH_HEADER = struct.Struct("<4sBBHIIQQII")
GATEWAY_HEADER = struct.Struct("<IHHI")


class Sink:
    def __init__(self, path):
        self.path = path
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.dropped = 0

    def send(self, data):
        try:
            self.socket.sendto(data, self.path)
            return True
        except OSError:
            self.dropped += 1
            return False

    def close(self):
        self.socket.close()


class Gateway:
    def __init__(self, path):
        self.path = path
        self.socket = None
        self.retry = 0

    def close(self):
        if self.socket:
            self.socket.close()
        self.socket = None

    def latest(self):
        now = time.monotonic()
        if self.socket is None:
            if now < self.retry:
                return None
            self.retry = now + 1
            try:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                self.socket.settimeout(0.02)
                self.socket.connect(self.path)
                self.socket.sendall(GATEWAY_HEADER.pack(0x4C4E5247, 1, 1, 0))
                self.socket.setblocking(False)
            except OSError:
                self.close()
                return None
        latest = None
        for _ in range(64):
            try:
                raw = self.socket.recv(256)
            except BlockingIOError:
                return latest
            except OSError:
                self.close()
                return (0.0, 0.0)
            if not raw:
                self.close()
                return (0.0, 0.0)
            if len(raw) != 29:
                continue
            magic, version, kind, size = GATEWAY_HEADER.unpack_from(raw)
            if (magic, version, kind, size) != (0x4C4E5247, 1, 8, 17):
                continue
            source, v, w = struct.unpack_from("<Bdd", raw, 12)
            if source == 3:
                latest = (0.0, 0.0)
            elif source in (1, 2) and math.isfinite(v) and math.isfinite(w):
                latest = (v, w)
        # A large queued backlog cannot establish command freshness.
        self.close()
        return (0.0, 0.0)

    def status(self, frame, geometry):
        if not self.socket or frame.kind != Kind.MOTOR or len(frame.payload) != 64:
            return
        p = frame.payload
        valid = struct.unpack_from("<I", p)[0]
        values = [0.0] * 10
        flags = 0
        if valid & 8:
            values[0] = struct.unpack_from("<H", p, 36)[0] / 10
            flags |= 1
        if geometry and valid & 2:
            left, right = struct.unpack_from("<ii", p, 12)
            scale = 2 * math.pi * geometry["radius_m"] / geometry["counts_per_rev"]
            left *= scale * geometry["left_sign"]
            right *= scale * geometry["right_sign"]
            values[5] = (left + right) / 2
            values[6] = (right - left) / geometry["track_m"]
            flags |= 8
        raw = struct.pack("<QI10d", time.time_ns() // 1_000_000, flags, *values)
        try:
            self.socket.send(GATEWAY_HEADER.pack(0x4C4E5247, 1, 9, len(raw)) + raw)
        except OSError:
            self.close()


def health_packet(device, link=None, connected=False):
    age = 0xFFFFFFFF
    raw = b"\0" * 88
    if link and link.health:
        age = min(0xFFFFFFFF, int((time.monotonic() - link.last_health) * 1000))
        raw = link.health.payload
    return (
        HEALTH_HEADER.pack(
            b"MCU2",
            device["role_id"],
            int(connected and age < 500),
            2,
            link.boot if link else 0,
            link.session if link else 0,
            time.time_ns() // 1_000_000,
            device["uid_int"],
            age,
            link.parser.errors if link else 0,
        )
        + raw
    )


def serve(device, args, stop, received):
    wheels = geometry(device)
    link = Link(device)
    gateway = Gateway(args.gateway) if device["role"] == "control" else None
    health, samples = Sink(args.health), Sink(args.samples)
    try:
        received.begin(link.boot, link.oldest)
        if gateway:
            link.configure(driver_packet(device))
        command = 0
        heartbeat = sync = last_ack = health_sent = 0.0
        started = time.monotonic()
        health_missing = False
        reported_missing = reported_full = 0
        while not stop[0]:
            now = time.monotonic()
            if now - heartbeat >= 0.1:
                link.send(Kind.HEALTH_REQUEST)
                heartbeat = now
            if now - sync >= (1 if link.offset_ns is None else 5):
                link.timesync()
                sync = now
            for f in link.poll():
                if f.kind in (Kind.IMU, Kind.MOTOR):
                    received.accept(f)
                    if gateway and link.offset_ns is not None:
                        stamp = f.stamp_us * 1000 + link.offset_ns
                        if -20_000_000 <= time.time_ns() - stamp <= 200_000_000:
                            gateway.status(f, wheels)
                elif f.kind == Kind.RESULT and len(f.payload) == 8 and f.payload[1]:
                    logging.warning(
                        "MCU rejected request type=%s seq=%s", f.payload[0], f.sequence
                    )
            received.advance(link.oldest)
            # RAM acceptance is the ACK boundary. Consumer lag uses this bounded queue.
            if now - last_ack >= 0.02:
                if received.ack:
                    link.send(Kind.ACK, struct.pack("<I", received.ack))
                last_ack = now
            if link.offset_ns is not None:
                for _ in range(128):
                    if not received.ready:
                        break
                    f = received.ready[0]
                    data = json.dumps(
                        dict(
                            role=device["role"],
                            uid=device["uid"],
                            boot=f.boot,
                            seq=f.sequence,
                            kind=f.kind,
                            stamp_ns=f.stamp_us * 1000 + link.offset_ns,
                            payload=f.payload.hex(),
                        )
                    ).encode()
                    if not samples.send(data):
                        break  # Keep the sample in RAM until the consumer accepts it.
                    received.pop()
            if now - health_sent >= 0.2:
                health.send(health_packet(device, link, True))
                health_sent = now
                if (
                    received.missing != reported_missing
                    or received.full != reported_full
                ):
                    logging.warning(
                        "receive buffer: missing=%d full_retries=%d",
                        received.missing,
                        received.full,
                    )
                    reported_missing, reported_full = received.missing, received.full
            motion = gateway.latest() if gateway else None
            if motion is not None:
                if motion == (0.0, 0.0):
                    link.send(Kind.STOP)
                elif wheels:
                    try:
                        left, right = wheel_command(wheels, *motion)
                    except ValueError as error:
                        link.send(Kind.STOP)
                        logging.warning("Rejected motion: %s", error)
                    else:
                        command += 1
                        link.send(
                            Kind.MOTION, struct.pack("<IiiI", command, left, right, 200)
                        )
            missing = now - (link.last_health or started) >= 1
            if missing and not health_missing:
                logging.warning("MCU health missing for 1s; reporting only")
            health_missing = missing
            time.sleep(0.001)
    finally:
        health.send(health_packet(device, link, False))
        link.close()
        if gateway:
            gateway.close()
        health.close()
        samples.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", default="/etc/loonar/mcu-registry.json")
    p.add_argument("--role", required=True, choices=("control", "payload"))
    p.add_argument("--runtime", default="/run/loonar/mcu")
    p.add_argument("--gateway", default="/run/loonar/vehicle-gateway/backend.sock")
    p.add_argument("--health", default="/run/loonar/mcu/health.sock")
    p.add_argument("--samples", default="/run/loonar/mcu/samples.sock")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    device = load(args.registry, args.role)
    Path(args.runtime).mkdir(parents=True, exist_ok=True)
    lock = open(Path(args.runtime) / f"{args.role}.lock", "a")
    received = ReceiveBuffer()
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stop = [False]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.__setitem__(0, True))
    while not stop[0]:
        try:
            serve(device, args, stop, received)
        except (OSError, ValueError, TimeoutError) as error:
            logging.error("%s: %s", args.role, error)
            sink = Sink(args.health)
            sink.send(health_packet(device))
            sink.close()
            for _ in range(10):
                if stop[0]:
                    break
                time.sleep(0.1)
    lock.close()


if __name__ == "__main__":
    main()
