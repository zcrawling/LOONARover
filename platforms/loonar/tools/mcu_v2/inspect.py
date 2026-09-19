"""User-run diagnostics. Discovery sends HELLO only; health never configures motion."""

import argparse
import json
import struct
import time
from .config import load, ROLES
from .link import Link
from .wire import Frame, Kind, Parser


def decode_health(raw):
    if len(raw) != 128 or raw[:4] != b"MCU2":
        raise ValueError("expected MCU2 health payload")
    _, role, online, version, boot, session, stamp, uid, age, host_errors = (
        struct.unpack_from("<4sBBHIIQQII", raw)
    )
    if role not in (1, 2) or version != 2:
        raise ValueError("invalid role/protocol")
    p = raw[40:]
    names = (
        "inhibit",
        "last_command",
        "link_progress",
        "driver_progress",
        "imu_progress",
        "rx_errors",
        "sample_drops",
        "priority_drops",
        "buffer_depth",
        "gyro_age_ms",
        "driver_ack_age_ms",
        "imu_resets",
        "rejected",
        "latest_sequence",
    )
    result = dict(
        role="control" if role == 1 else "payload",
        uid=f"{uid:016x}",
        online=bool(online),
        boot=boot,
        session=session,
        host_stamp_ms=stamp,
        health_age_ms=age,
        host_errors=host_errors,
        uptime_ms=struct.unpack_from("<Q", p, 8)[0],
        temperature_c=struct.unpack_from("<f", p, 16)[0],
    )
    result.update(zip(names, struct.unpack_from("<14I", p, 20)))
    result.update(
        transport=p[76],
        identity_bound=bool(p[77]),
        driver_failures=struct.unpack_from("<I", p, 80)[0],
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--role", choices=tuple(ROLES), required=True)
    p.add_argument(
        "--discover-device",
        help="explicit serial path: HELLO only, no configuration/flash",
    )
    p.add_argument("--registry", default="/etc/loonar/mcu-registry.json")
    p.add_argument("--seconds", type=float, default=5)
    args = p.parse_args()
    if args.discover_device:
        import serial

        with serial.Serial(
            args.discover_device,
            2000000,
            timeout=0.05,
            write_timeout=0.1,
            exclusive=True,
        ) as port:
            port.write(Frame(ROLES[args.role], Kind.HELLO_REQUEST, sequence=1).encode())
            parser = Parser()
            end = time.monotonic() + 2
            while time.monotonic() < end:
                for f in parser.feed(port.read(4096)):
                    if (
                        f.role == ROLES[args.role]
                        and f.kind == Kind.HELLO
                        and len(f.payload) == 28
                    ):
                        uid, expected, oldest, latest, flags = struct.unpack_from(
                            "<QQIII", f.payload
                        )
                        print(
                            json.dumps(
                                dict(
                                    role=args.role,
                                    uid=f"{uid:016x}",
                                    expected=f"{expected:016x}",
                                    boot=f.boot,
                                    bound=bool(flags & 1),
                                ),
                                indent=2,
                            )
                        )
                        return
        raise TimeoutError("no v2 discovery reply on the specified device")
    from .backend import health_packet

    device = load(args.registry, args.role)
    link = Link(device)
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            seq = link.send(Kind.HEALTH_REQUEST)
            link.wait(Kind.HEALTH, 0.5, seq)
            print(json.dumps(decode_health(health_packet(device, link, True))))
            time.sleep(0.1)
    finally:
        link.close()


if __name__ == "__main__":
    main()
