"""Single central configuration; changes apply after restart."""
import math
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/gcs.toml"
LOCAL_SOCKET = ROOT / ".runtime/backend.sock"


def load_manual_control(path=DEFAULT_CONFIG):
    """Load the real-rover keyboard values without enabling the Mock backend."""
    with open(path, "rb") as stream:
        section = tomllib.load(stream)["manual_control"]
    result = dict(section)
    for key in ("linear_speed_mps", "angular_speed_radps"):
        value = result[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"manual_control.{key}: must be positive and finite")
        result[key] = float(value)
    interval = result.get("repeat_interval_ms")
    if type(interval) is not int or not 50 <= interval <= 1000:
        raise ValueError("manual_control.repeat_interval_ms: must be an integer from 50 to 1000")
    expected = {
        "forward_key": "PAGE_UP",
        "left_key": "HOME",
        "reverse_key": "PAGE_DOWN",
        "right_key": "END",
        "stop_key": "SPACE",
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"manual_control.{key}: must be {value!r}")
    return result


def load(path=DEFAULT_CONFIG):
    with open(path, "rb") as stream:
        c = tomllib.load(stream)
    if c["network"]["target"] != "mock":
        raise ValueError("Real rover protocol is not implemented; target must be mock")
    if c["network"]["host"] not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("Mock adapter only permits loopback addresses")
    for section, key in (("network", "port"), ("video", "port")):
        value = c[section][key]
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError(f"{section}.{key}: invalid port")
    for section, keys in {
        "network": ["connect_timeout", "write_timeout"],
        "heartbeat": ["interval", "degraded_after", "disconnect_after"],
        "command": ["payload_receipt_timeout"],
        "display": ["refresh", "stale_after"],
        "mock": ["status_interval", "sample_interval", "payload_duration"],
    }.items():
        for key in keys:
            v = c[section][key]
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"{section}.{key}: must be positive and finite")
    h = c["heartbeat"]
    if not h["interval"] < h["degraded_after"] < h["disconnect_after"]:
        raise ValueError("Heartbeat must satisfy interval < degraded < disconnect")
    delays = c["network"]["reconnect_delays"]
    if not delays or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in delays):
        raise ValueError("Reconnect delays must be positive finite numbers")
    for key in ("receipt_delay", "disconnect_after"):
        v = c["mock"][key]
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            raise ValueError(f"mock.{key}: must be nonnegative")
    for key in ("keepidle", "keepinterval", "keepcount"):
        if type(c["tcp"][key]) is not int or c["tcp"][key] <= 0:
            raise ValueError(f"tcp.{key}: must be positive integer")
    if type(c["tcp"]["user_timeout_ms"]) is not int or c["tcp"]["user_timeout_ms"] < 0:
        raise ValueError("tcp.user_timeout_ms: must be nonnegative integer")
    if type(c["display"]["event_limit"]) is not int or not 1 <= c["display"]["event_limit"] <= 1000:
        raise ValueError("event_limit must be 1..1000")
    return c
