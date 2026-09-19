"""Device identity, RoboClaw UART settings, and Pi-side wheel conversion."""

import json
import math
import re
import struct
from pathlib import Path

ROLES = {"control": 1, "payload": 2}
# User-confirmed: 196 mm wheels, 210 mm track, counts per output/wheel revolution.
CONTROL_GEOMETRY = {
    "radius_m": 0.098,
    "track_m": 0.210,
    "counts_per_rev": 485681,
    "left_sign": 1,
    "right_sign": 1,
}


def load(path, role):
    config = json.loads(Path(path).read_text())
    if role not in ROLES or config.get("schema") != 2:
        raise ValueError("expected registry schema 2 and control/payload role")
    devices = config["devices"]
    uids = [d["uid"].lower() for d in devices.values()]
    paths = [d["device"] for d in devices.values()]
    if len(set(uids)) != len(uids) or len(set(paths)) != len(paths):
        raise ValueError("each MCU needs a unique UID and device path")
    for uid in uids:
        if not re.fullmatch("[0-9a-f]{16}", uid) or int(uid, 16) == 0:
            raise ValueError("register the actual nonzero MCU UIDs first")
    d = dict(devices[role])
    d.update(
        role=role, role_id=ROLES[role], uid=d["uid"].lower(), uid_int=int(d["uid"], 16)
    )
    if d.get("transport") not in ("usb", "uart") or not d["device"].startswith("/dev/"):
        raise ValueError("explicit /dev path and usb/uart transport required")
    if d["transport"] == "usb" and not d["device"].startswith("/dev/serial/by-id/"):
        raise ValueError("use the MCU's stable /dev/serial/by-id path")
    return d


def driver_packet(device):
    d = device.get("roboclaw", {})
    baud, address = d.get("baud", 115200), d.get("address", 128)
    if baud not in (38400, 57600, 115200, 230400, 460800) or not 128 <= address <= 135:
        raise ValueError("invalid RoboClaw baud/address")
    return struct.pack("<IB3x", baud, address)


def geometry(device):
    g = device.get("geometry")
    if not g:
        return None
    values = [float(g[name]) for name in ("radius_m", "track_m", "counts_per_rev")]
    # Legacy registries used all zeros for an unconfigured wheel conversion.
    if all(value == 0 for value in values):
        return None
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("wheel radius, track and counts/rev must be positive")
    if g["left_sign"] not in (-1, 1) or g["right_sign"] not in (-1, 1):
        raise ValueError("wheel signs must be -1 or 1")
    return dict(
        zip(("radius_m", "track_m", "counts_per_rev"), values),
        left_sign=g["left_sign"],
        right_sign=g["right_sign"],
    )


def wheel_command(g, linear, angular):
    if not g:
        raise ValueError("wheel conversion is not configured")
    if not math.isfinite(linear) or not math.isfinite(angular):
        raise ValueError("nonfinite motion command")
    scale = g["counts_per_rev"] / (2 * math.pi * g["radius_m"])
    left = (linear - angular * g["track_m"] / 2) * scale * g["left_sign"]
    right = (linear + angular * g["track_m"] / 2) * scale * g["right_sign"]
    if any(
        not math.isfinite(v) or v < -2147483648 or v > 2147483647 for v in (left, right)
    ):
        raise ValueError("wheel command exceeds the RoboClaw signed 32-bit field")
    return round(left), round(right)
