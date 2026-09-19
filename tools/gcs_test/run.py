#!/usr/bin/env python3
"""Run the real cFS/GroundLink + gateway on a PC, without ROS."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'build/gcs-test'
CFS = WORK / 'cFS'
REV = '088b2fa828db9ff7e00733f1908e0eeb59f66ce3'  # NASA cFS v7.0.1


def build(run_tests=True, jobs=4):
    def run(argv, cwd=ROOT):
        with (WORK / 'build.log').open('a') as log:
            subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(f'Building (first run downloads NASA cFS v7.0.1). Log: {WORK}/build.log', flush=True)
    if not CFS.exists():
        run(['git', 'clone', '--branch', 'v7.0.1', '--depth', '1',
             'https://github.com/nasa/cFS.git', str(CFS)])
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=CFS, text=True).strip()
    if actual != REV:
        raise RuntimeError(f'Unexpected cFS revision: {actual}; expected {REV}')
    run(['git', 'submodule', 'update', '--init', '--recursive', '--depth', '1',
         'cfe', 'osal', 'psp', 'tools/elf2cfetbl',
         'tools/tblCRCTool', 'tools/commandline-tools'], CFS)
    defs = CFS / 'loonar_defs'
    shutil.copytree(CFS / 'sample_defs', defs, dirs_exist_ok=True)
    (defs / 'targets.cmake').write_text('''set(MISSION_NAME "LOONAR_PC_Test")
set(SPACECRAFT_ID 0x42)
set(MISSION_CPUNAMES cpu1)
set(cpu1_PROCESSORID 1)
set(cpu1_SYSTEM native)
set(MISSION_GLOBAL_APPLIST loonar_ground_link loonar_vehicle_adapter loonar_mcu_bridge)
''')
    (defs / 'cpu1/install_custom.cmake').write_text('''install(FILES ${MISSION_DEFS}/cfe_es_startup.scr
    DESTINATION ${TGTNAME}/${INSTALL_SUBDIR})
''')
    # cFE startup scripts do not recognize shell-style # comments.
    fragment = (ROOT / 'cfs/mission/cfe_es_startup.scr.fragment').read_text()
    (defs / 'cfe_es_startup.scr').write_text('\n'.join(
        line for line in fragment.splitlines() if line.strip().startswith('CFE_')) + '\n')
    for name, source in [('loonar_ground_link', 'ground_link'),
                         ('loonar_vehicle_adapter', 'vehicle_adapter'), ('loonar_mcu_bridge', 'mcu_bridge'), ('common', 'common')]:
        dest = CFS / 'apps' / name
        if not dest.is_symlink():
            dest.symlink_to(ROOT / 'cfs/apps' / source, target_is_directory=True)
    run(['cmake', '-S', str(ROOT), '-B', str(WORK / 'host'),
         '-DBUILD_TESTING=' + ('ON' if run_tests else 'OFF')])
    run(['cmake', '--build', str(WORK / 'host'), '-j', str(jobs)])
    if run_tests:
        run(['ctest', '--test-dir', str(WORK / 'host'), '--output-on-failure'])
    run(['make', 'native_std.prep',
         'PREP_OPTS_native_std=-DSIMULATION=native -DCFE_EDS_ENABLED=OFF '
         '-DMISSIONCONFIG=loonar -DCMAKE_BUILD_TYPE=Debug -DENABLE_UNIT_TESTS=OFF'], CFS)
    run(['make', 'native_std.install', 'SIMULATION=native'], CFS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcs-ip', help='Video destination IP/hostname (GCS computer)')
    parser.add_argument('--video', choices=['none', 'test', 'camera'], default='none')
    parser.add_argument('--video-device', default='/dev/video0', help='V4L2 camera, MJPEG 640x480')
    parser.add_argument('--video-port', type=int, default=5600)
    parser.add_argument('--battery-voltage', type=float, default=11.7, help='Synthetic test voltage, sent once/sec')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--skip-tests', action='store_true',
                        help='Only with --build-only: compile without running tests or processes')
    parser.add_argument('--jobs', type=int, default=4, help='Host build parallelism')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.skip_tests and (not args.build_only or args.skip_build):
        parser.error('--skip-tests requires --build-only and cannot be used with --skip-build')
    if args.video != 'none' and not args.gcs_ip:
        parser.error('--gcs-ip is required with --video test/camera')
    if not 1 <= args.video_port <= 65535:
        parser.error('--video-port must be 1..65535')
    WORK.mkdir(parents=True, exist_ok=True)
    lock = (WORK / 'run.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('A GCS test launcher is already running') from None
    if not args.skip_build:
        build(run_tests=not args.skip_tests, jobs=args.jobs)
    if args.build_only:
        return
    cpu = CFS / 'build-native_std/exe/cpu1'
    gateway = WORK / 'host/common/vehicle_gateway/vehicle_gatewayd'
    ctl = gateway.with_name('vehicle_gatewayctl')
    for binary in [cpu / 'core-cpu1', gateway, ctl]:
        if not binary.is_file():
            raise RuntimeError(f'Missing {binary}; run without --skip-build')
    # Do not disturb another GroundLink instance.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('0.0.0.0', 7443))
    runtime = Path(f'/tmp/loonar-gcs-test-{os.getuid()}')
    runtime.mkdir(mode=0o700, exist_ok=True)
    if runtime.is_symlink() or runtime.stat().st_uid != os.getuid():
        raise RuntimeError(f'Invalid runtime directory: {runtime}')
    env = dict(os.environ, LOONAR_GATEWAY_SOCKET=str(runtime / 'cfs.sock'),
               LOONAR_MCU_HEALTH_SOCKET=str(runtime / 'mcu-health.sock'))
    processes = []
    logs = []

    def start(name, command, cwd=ROOT):
        log = (WORK / f'{name}.log').open('w')
        logs.append(log)
        p = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((name, p))
        return p

    def healthy():
        for name, p in processes:
            if p.poll() is not None:
                raise RuntimeError(f'{name} exited ({p.returncode}); see {WORK}/{name}.log')

    def stop_signal(_sig, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    try:
        start('gateway', ['stdbuf', '-oL', str(gateway), '--runtime-dir', str(runtime)])
        deadline = time.monotonic() + 10
        while not (runtime / 'cfs.sock').exists():
            healthy()
            if time.monotonic() > deadline:
                raise RuntimeError('Gateway socket startup timeout')
            time.sleep(.1)
        start('cfs', [str(cpu / 'core-cpu1')], cwd=cpu)
        deadline = time.monotonic() + 30
        while True:
            healthy()
            try:
                with socket.create_connection(('127.0.0.1', 7443), timeout=2) as probe:
                    # READY requires telemetry through the adapter, not just an open port.
                    data = bytearray()
                    ready = False
                    while not ready and time.monotonic() < deadline:
                        chunk = probe.recv(4096)
                        if not chunk:
                            raise OSError('GroundLink closed the readiness probe')
                        data.extend(chunk)
                        while len(data) >= 16:
                            magic, version, kind, _, size = struct.unpack_from('<4sHHII', data)
                            if magic != b'LNK1' or version != 1 or size > 512:
                                raise RuntimeError('Invalid GroundLink startup telemetry')
                            if len(data) < 16 + size:
                                break
                            ready = ready or (kind == 0x8002 and size == 20)
                            del data[:16 + size]
                    if not ready:
                        raise OSError('No gateway telemetry')
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f'cFS TCP 7443 startup timeout; see {WORK}/cfs.log')
                time.sleep(.2)
        if args.video != 'none':
            source = (['videotestsrc', 'is-live=true', '!', 'video/x-raw,width=640,height=360,framerate=30/1']
                      if args.video == 'test' else
                      ['v4l2src', f'device={args.video_device}', '!',
                       'image/jpeg,width=640,height=480,framerate=30/1', '!', 'jpegdec'])
            start('video', ['gst-launch-1.0', '-e', *source,
                  '!', 'queue', 'max-size-buffers=2', 'leaky=downstream',
                  '!', 'videoconvert', '!', 'video/x-raw,format=I420',
                  '!', 'x264enc', 'tune=zerolatency', 'speed-preset=ultrafast',
                  'bitrate=1000', 'key-int-max=30', 'bframes=0',
                  '!', 'h264parse', 'config-interval=1', '!', 'mpegtsmux', 'alignment=7',
                  '!', 'udpsink', f'host={args.gcs_ip}', f'port={args.video_port}',
                  'sync=true', 'async=false'])
        time.sleep(1)
        healthy()
        ips = subprocess.check_output(['hostname', '-I'], text=True).strip()
        print(f'\nREADY: real cFS + vehicle_gatewayd (no ROS)\n'
              f'Control: TCP <this-PC-IP>:7443 (bind 0.0.0.0)\n'
              f'This PC IP addresses: {ips}\n'
              f'Local gateway sockets: {runtime}/{{cfs,ros,backend}}.sock\n'
              f'Telemetry: synthetic battery={args.battery_voltage} V, 1 Hz; other vehicle fields unknown\n'
              f'Video: {args.video}' +
              (f' -> UDP {args.gcs_ip}:{args.video_port}' if args.video != 'none' else '') +
              f'\nLogs: {WORK}/{{gateway,cfs,video}}.log\n'
              'One GroundLink client at a time. Ctrl+C stops all test processes.\n', flush=True)
        while True:
            healthy()
            subprocess.run([str(ctl), 'vehicle-status', str(runtime / 'backend.sock'),
                            str(args.battery_voltage)], check=True, stdout=subprocess.DEVNULL)
            time.sleep(1)
    finally:
        for _, p in reversed(processes):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for _, p in reversed(processes):
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nGCS test stopped.')
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}\nBuild log: {WORK}/build.log', file=sys.stderr)
        sys.exit(1)
