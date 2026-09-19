"""User-started Gateway -> Control MCU bench; prints motor feedback, sends no motion."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import time

from .config import load, geometry
from .inspect import decode_health


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=Path.home() / "loonar-motor-bench/runtime")
    parser.add_argument("--gateway-bin", type=Path, default=Path("/opt/loonar/current/bin/vehicle_gatewayd"))
    args = parser.parse_args()
    device = load(args.registry, "control")
    if geometry(device) is None:
        raise ValueError("Fill actual radius_m, track_m and counts_per_rev in the registry first")
    if not args.gateway_bin.is_file():
        raise ValueError(f"Gateway executable not found: {args.gateway_bin}")
    if subprocess.run(["systemctl", "is-active", "--quiet", "loonar-mcu@control.service"]).returncode == 0:
        raise ValueError("Stop loonar-mcu@control.service before starting this bench")
    runtime = args.runtime.expanduser().resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    lock = open(runtime / "bench.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gateway_dir = runtime / "gateway"
    gateway_dir.mkdir(exist_ok=True)
    sockets, children, logs = [], [], []
    stop = [False]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.__setitem__(0, True))
    try:
        for name in ("samples", "health"):
            path = runtime / f"{name}.sock"
            path.unlink(missing_ok=True)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(str(path))
            sock.setblocking(False)
            sockets.append(sock)
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + environment.get("PYTHONPATH", "")
        commands = [
            [str(args.gateway_bin), "--runtime-dir", str(gateway_dir)],
            [sys.executable, "-m", "mcu_v2.backend", "--role", "control",
             "--registry", str(args.registry.resolve()), "--runtime", str(runtime),
             "--gateway", str(gateway_dir / "backend.sock"),
             "--samples", str(runtime / "samples.sock"), "--health", str(runtime / "health.sock")],
        ]
        for name, command in zip(("gateway", "backend"), commands):
            log = open(runtime / f"{name}.log", "w")
            logs.append(log)
            children.append(subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT))
        print(f"Started bench processes. Wait for online health and fresh motor feedback.\n"
              f"Command socket: {gateway_dir / 'cfs.sock'}\nLogs: {runtime}\n"
              "M1=right, M2=left. Ctrl-C stops the backend and gateway.", flush=True)
        last_motor = last_health = 0.0
        while not stop[0]:
            if any(child.poll() is not None for child in children):
                raise RuntimeError(f"A bench process exited; inspect {runtime}/*.log")
            ready, _, _ = select.select(sockets, [], [], 0.1)
            for sock in ready:
                raw = sock.recv(65536)
                now = time.monotonic()
                if sock is sockets[1]:
                    status = decode_health(raw)
                    if now - last_health >= 1:
                        print("health", json.dumps({key: status[key] for key in
                              ("online", "uid", "temperature_c", "inhibit", "driver_ack_age_ms", "sample_drops")}), flush=True)
                        last_health = now
                else:
                    sample = json.loads(raw)
                    # Drain all IMU/motor samples so RAM queues keep advancing.
                    if sample["kind"] == 33 and now - last_motor >= 1:
                        payload = bytes.fromhex(sample["payload"])
                        valid, left_count, right_count, left_speed, right_speed, left_cmd, right_cmd = struct.unpack_from("<I6i", payload)
                        print(f"motor age_ms={(time.time_ns()-sample['stamp_ns'])/1e6:.0f} valid=0x{valid:02x} "
                              f"left(M2) command/speed/count={left_cmd}/{left_speed}/{left_count} "
                              f"right(M1) command/speed/count={right_cmd}/{right_speed}/{right_count} "
                              f"error=0x{struct.unpack_from('<I', payload, 44)[0]:08x}", flush=True)
                        last_motor = now
    finally:
        # Stop the serial owner first so its normal close sends MCU STOP.
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for sock in sockets:
            path = Path(sock.getsockname())
            sock.close()
            path.unlink(missing_ok=True)
        for log in logs:
            log.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
