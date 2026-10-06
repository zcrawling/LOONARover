"""Hardware-only probe: validate helper packets without ROS or motor access."""

import argparse
import array
import json
import os
import selectors
import signal
import struct
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("helper")
    parser.add_argument("--seconds", type=float, default=20)
    args = parser.parse_args()
    child = subprocess.Popen([args.helper, "1"], stdout=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    buf = bytearray()
    frames = 0
    first = last = previous = None
    header = struct.Struct("<4IQ12d")
    started = time.monotonic()
    summary = {}
    try:
        while time.monotonic() - started < args.seconds:
            if not selector.select(0.2):
                if child.poll() is not None:
                    break
                continue
            chunk = os.read(child.stdout.fileno(), 1024 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            while len(buf) >= header.size:
                magic, w, h, seq, stamp, *cal = header.unpack_from(buf)
                assert magic == 0x4C544F46 and 0 < w <= 1920 and 0 < h <= 1080
                assert previous is None or seq > previous
                size = header.size + w * h * 4
                if len(buf) < size:
                    break
                assert cal[0] > 0 and cal[1] > 0
                now = time.monotonic()
                if first is None:
                    first = now
                    depth = array.array("H", buf[header.size : header.size + w * h * 2])
                    amplitude = array.array("H", buf[header.size + w * h * 2 : size])
                    valid = [v for v in depth if 0 < v < 65535]
                    summary.update(
                        width=w,
                        height=h,
                        intrinsics=cal[:4],
                        depth_u16_min=min(valid) if valid else None,
                        depth_u16_max=max(valid) if valid else None,
                        amplitude_max=max(amplitude),
                        startup_seconds=round(first - started, 3),
                    )
                last = now
                previous = seq
                frames += 1
                del buf[:size]
    finally:
        child.send_signal(signal.SIGTERM)
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        child.stdout.close()
        selector.close()
    summary.update(
        frames=frames,
        helper_exit=child.returncode,
        hz=round((frames - 1) / (last - first), 2) if frames > 1 else 0,
    )
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if frames >= 10 and child.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
