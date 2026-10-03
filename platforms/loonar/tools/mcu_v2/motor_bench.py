"""User-started Gateway -> Control MCU bench; prints motor feedback, sends no motion."""

import argparse
import fcntl
import json
import ipaddress
import logging
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
    parser.add_argument("--cfs-dir", type=Path, help="Start real cFS from this prepared cpu1 directory")
    parser.add_argument("--video-ip", help="Also stream camera video to this GCS IPv4 address")
    parser.add_argument("--ros-samples", action="store_true", help="Publish MCU samples to ROS (no recording)")
    parser.add_argument("--encoder-verify", action="store_true", help="Compare and record command/encoder feedback without sending motion")
    parser.add_argument("--record", action="store_true", help="Publish MCU ROS samples and record available ROS topics to ~/loonar-bags")
    parser.add_argument("--record-video", action="store_true", help="Record Pi camera H.264 video locally, with or without --video")
    parser.add_argument("--video-record-dir", type=Path, default=Path.home() / "loonar-videos")
    parser.add_argument("--payload-device", type=Path, help="Run Payload ASCII service for this USB by-id device")
    args = parser.parse_args()
    if args.record:
        args.ros_samples = True
    device = load(args.registry, "control")
    if geometry(device) is None:
        raise ValueError("Fill actual radius_m, track_m and counts_per_rev in the registry first")
    if not args.gateway_bin.is_file():
        raise ValueError(f"Gateway executable not found: {args.gateway_bin}")
    if args.video_ip:
        args.video_ip = str(ipaddress.IPv4Address(args.video_ip))
    if args.video_ip or args.record_video:
        if subprocess.run(["systemctl", "is-active", "--quiet", "loonar-video.service"]).returncode == 0:
            raise ValueError("Stop loonar-video.service before starting this script's video sender")
    if args.cfs_dir:
        args.cfs_dir = args.cfs_dir.expanduser().resolve()
        for name in ("core-cpu1", "cf/lnr_ground.so", "cf/lnr_vehicle.so", "cf/lnr_mcu.so", "cf/cfe_es_startup.scr"):
            if not (args.cfs_dir / name).is_file():
                raise ValueError(f"Missing {args.cfs_dir / name}; run prepare-ground-control.sh once")
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", 7443))
    if subprocess.run(["systemctl", "is-active", "--quiet", "loonar-mcu@control.service"]).returncode == 0:
        raise ValueError("Stop loonar-mcu@control.service before starting this bench")
    if args.payload_device and args.cfs_dir and not (args.cfs_dir / "cf/lnr_payload.so").is_file():
        raise ValueError("Rebuild cFS with PayloadAdapter before using --payload-device")
    if args.payload_device and subprocess.run(["systemctl", "is-active", "--quiet", "loonar-payload-pca.service"]).returncode == 0:
        raise ValueError("Stop loonar-payload-pca.service before using --payload-device")
    runtime = args.runtime.expanduser().resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    lock = open(runtime / "bench.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gateway_dir = runtime / "gateway"
    gateway_dir.mkdir(exist_ok=True)
    sockets, children, logs = [], [], []
    named_children = []
    reported_exits = set()
    ros_samples = None
    encoder_verify = None
    recorder = None
    stop = [False]
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.__setitem__(0, True))
    forward = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) if args.cfs_dir else None
    if forward:
        forward.setblocking(False)
    try:
        if args.encoder_verify:
            from .encoder_verify import EncoderVerify

            encoder_verify = EncoderVerify(runtime / f"encoder-{time.time_ns()}.csv")
        for name in ("samples", "health"):
            path = runtime / f"{name}.sock"
            path.unlink(missing_ok=True)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(str(path))
            sock.setblocking(False)
            sockets.append(sock)
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + environment.get("PYTHONPATH", "")
        environment["LOONAR_GATEWAY_SOCKET"] = str(gateway_dir / "cfs.sock")
        environment["LOONAR_MCU_HEALTH_SOCKET"] = str(runtime / "cfs-health.sock")
        if args.payload_device:
            environment["LOONAR_PAYLOAD_PCA_SOCKET"] = str(runtime / "payload-pca.sock")
        if args.ros_samples:
            from .ros_samples import RosSamples

            ros_samples = RosSamples(runtime, args.registry.resolve(), environment)
            try:
                ros_samples.start()
            except OSError:
                logging.exception("Could not start ROS publisher; driving processes will continue")
                ros_samples.close()
                ros_samples = None
        commands = [
            ("gateway", [str(args.gateway_bin.resolve()), "--runtime-dir", str(gateway_dir)], None),
        ]
        if args.payload_device:
            commands.append(("payload", [sys.executable,
                str(Path(__file__).resolve().parents[1] / "payload_pca_service.py"),
                "--device", str(args.payload_device), "--socket", str(runtime / "payload-pca.sock"),
                "--log-dir", str(runtime / "payload")], None))
        if args.cfs_dir:
            commands.append(("cfs", [str(args.cfs_dir / "core-cpu1")], args.cfs_dir))
        commands.append(("backend", [sys.executable, "-m", "mcu_v2.backend", "--role", "control",
             "--registry", str(args.registry.resolve()), "--runtime", str(runtime),
             "--gateway", str(gateway_dir / "backend.sock"),
             "--samples", str(runtime / "samples.sock"), "--health", str(runtime / "health.sock")], None))
        if args.video_ip or args.record_video:
            video_config = runtime / "video.env"
            video_config.write_text(f"GROUND_STATION_IP={args.video_ip or ''}\nVIDEO_PORT=5600\n"
                                    "VIDEO_SOURCE=libcamera\nVIDEO_PROFILE=low\nVIDEO_ENCODER_THREADS=1\n")
            environment["LOONAR_VIDEO_CONFIG"] = str(video_config)
            environment["VIDEO_STREAM_ENABLED"] = "1" if args.video_ip else "0"
            environment["VIDEO_RECORD_PATH"] = ""
            if args.record_video:
                directory = args.video_record_dir.expanduser().resolve()
                directory.mkdir(parents=True, exist_ok=True)
                recording = directory / f"camera-{time.time_ns()}.ts"
                environment["VIDEO_RECORD_PATH"] = str(recording)
                print(f"Camera recording path: {recording}; status: {runtime}/video.log", flush=True)
            video_script = Path(__file__).resolve().parents[2] / "deploy/run-video.sh"
            commands.append(("video", ["bash", str(video_script)], None))
        if args.record:
            record_script = Path(__file__).resolve().parents[1] / "record-drive.sh"
            commands.append(("record", ["bash", str(record_script)], None))
        for name, command, cwd in commands:
            log = open(runtime / f"{name}.log", "w")
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT))
            named_children.append((name, children[-1]))
            if name == "record":
                recorder = children[-1]
                print(f"ROS recording requested: ~/loonar-bags; log: {runtime}/record.log", flush=True)
        print(f"Started bench processes. Wait for online health and fresh motor feedback.\n"
              f"Command socket: {gateway_dir / 'cfs.sock'}\nLogs: {runtime}\n"
              "M1=right, M2=left. Ctrl-C stops the backend and gateway.", flush=True)
        if args.cfs_dir:
            print("GroundLink: TCP <Pi-IP>:7443. MCU health is forwarded to cFS.\n"
                  "No motion command sent. Wait for online health before using the GCS.", flush=True)
        last_motor = last_health = last_imu = 0.0
        imu_values = {}
        imu_boot = None
        while not stop[0]:
            if ros_samples:
                ros_samples.poll()
            for name, child in named_children:
                code = child.poll()
                if code is None or name in reported_exits:
                    continue
                reported_exits.add(name)
                if name in ("video", "record", "payload"):
                    logging.error("%s exited (code=%s); inspect %s/%s.log. "
                                  "Control continues; this optional output is unavailable.", name, code, runtime, name)
                else:
                    raise RuntimeError(f"{name} exited (code={code}); inspect {runtime}/{name}.log")
            ready, _, _ = select.select(sockets, [], [], 0.1)
            for sock in ready:
                raw = sock.recv(65536)
                now = time.monotonic()
                if sock is sockets[1]:
                    status = decode_health(raw)
                    if forward:
                        try:
                            forward.sendto(raw, environment["LOONAR_MCU_HEALTH_SOCKET"])
                        except OSError:
                            pass  # cFS publishes offline if its health ingress stops receiving.
                    if now - last_health >= 1:
                        print("health", json.dumps({key: status[key] for key in
                              ("online", "uid", "temperature_c", "inhibit", "driver_ack_age_ms", "sample_drops", "imu_progress", "gyro_age_ms", "imu_resets")}), flush=True)
                        last_health = now
                else:
                    if ros_samples:
                        ros_samples.forward(raw)
                    sample = json.loads(raw)
                    if encoder_verify and sample["kind"] == 33:
                        encoder_verify.feed(sample)
                    if sample["kind"] == 32:
                        from .imu import decode_imu
                        try:
                            decoded = decode_imu(bytes.fromhex(sample["payload"]))
                        except ValueError as error:
                            logging.warning("Invalid IMU sample: %s", error)
                            continue
                        age_ms = (time.time_ns() - sample["stamp_ns"]) / 1e6
                        if sample["boot"] != imu_boot:
                            imu_values.clear()
                            imu_boot = sample["boot"]
                        if -20 <= age_ms <= 200:
                            imu_values[decoded["sensor"]] = decoded
                            if now - last_imu >= 1 and decoded["sensor"] == "quaternion_xyzw":
                                print("imu age_ms=%.0f %s" % (age_ms, json.dumps(imu_values)), flush=True)
                                last_imu = now
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
            if child is recorder:
                continue
            if child.poll() is None:
                if any(name == "video" and proc is child for name, proc in named_children):
                    child.send_signal(signal.SIGINT)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        if recorder is not None and recorder.poll() is None:
            # rosbag2 flushes storage and metadata on SIGINT.
            recorder.send_signal(signal.SIGINT)
            try:
                recorder.wait(timeout=15)
            except subprocess.TimeoutExpired:
                logging.error("Recorder did not finish within 15s; check bag metadata before analysis")
                recorder.terminate()
                try:
                    recorder.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.wait()
        if ros_samples:
            ros_samples.close()
        if encoder_verify:
            encoder_verify.close()
        for sock in sockets:
            path = Path(sock.getsockname())
            sock.close()
            path.unlink(missing_ok=True)
        for log in logs:
            log.close()
        if forward:
            forward.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
