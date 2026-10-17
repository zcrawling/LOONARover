#!/usr/bin/env python3
"""Manually stream a CubeEye depth preview as H.264/MPEG-TS over UDP."""
import argparse
import fcntl
import ipaddress
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import threading
import time

import cv2
import numpy as np


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise EOFError('CubeEye capture ended')
        data.extend(part)
    return data


def preview(depth, maximum):
    valid = (depth > 0) & (depth < 65535)
    gray = (np.clip(depth.astype(np.float32) / maximum, 0, 1) * 255).astype(np.uint8)
    color = cv2.applyColorMap(255 - gray, cv2.COLORMAP_TURBO)
    color[~valid] = 0
    cv2.putText(color, f'Depth: 0..{maximum} raw | valid {valid.mean()*100:.0f}%',
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
    return color


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', nargs='?', default='10.254.25.3')
    parser.add_argument('--port', type=int, default=5602)
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--bitrate', type=int, default=1000, help='H.264 kbit/s')
    parser.add_argument('--max-depth', type=int, default=3000, help='SDK native depth units')
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get(
        'LOONAR_CUBEEYE_SDK', '/opt/loonar/vendor/cubeeye/2.5.9/release')))
    parser.add_argument('--helper', type=Path, help='Use an already compiled capture helper')
    args = parser.parse_args()
    try:
        ipaddress.IPv4Address(args.destination)
    except ValueError:
        parser.error('destination must be an IPv4 address')
    if not (1 <= args.port <= 65535 and 1 <= args.fps <= 30
            and 1 <= args.bitrate <= 20000 and 1 <= args.max_depth <= 65534):
        parser.error('invalid port/fps/bitrate/depth range')
    # Do not stop or steal a camera from another owner.
    owner = subprocess.run(['pgrep', '-x', 'capture_xyz'], stdout=subprocess.DEVNULL)
    terrain = subprocess.run(['pgrep', '-x', 'cubeeye_capture'], stdout=subprocess.DEVNULL)
    if owner.returncode == 0 or terrain.returncode == 0:
        parser.error('ToF acquisition is already running; stop its owner before this standalone test')
    lock_path = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp')) / f'loonar-tof-stream-{os.getuid()}.lock'
    lock = lock_path.open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('another standalone ToF stream is running')
    sdk = args.sdk.resolve()
    libdirs = [sdk/'lib', sdk/'thirdparty/liblive555/lib/Release',
               *[p for p in (sdk/'thirdparty').glob('*/lib') if p.parent.name != 'python']]
    env = dict(os.environ, LD_LIBRARY_PATH=':'.join(map(str, libdirs)))
    helper = args.helper
    if helper is None:
        if not (sdk/'include/CubeEye/CubeEyeCamera.h').is_file():
            parser.error(f'SDK missing: {sdk}; supply --sdk /path/to/release')
        build = Path.home()/'.cache/loonar-tof-stream'
        build.mkdir(parents=True, exist_ok=True)
        helper = build/'capture'
        source = Path(__file__).resolve().parents[1]/'cubeeye_viewer/capture.cpp'
        subprocess.run(['g++', '-std=c++17', '-O2', '-pthread', str(source),
                        '-I'+str(sdk/'include/CubeEye'), '-L'+str(sdk/'lib'), '-lCubeEye',
                        *['-Wl,-rpath-link,'+str(p) for p in libdirs], '-o', str(helper)],
                       env=env, check=True)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    latest = [None, 0, 0.0]
    guard = threading.Lock()
    errors = []
    read_fd, write_fd = os.pipe()
    capture = encoder = None
    try:
        capture = subprocess.Popen([str(helper.resolve()), str(write_fd)],
                                   pass_fds=(write_fd,), env=env)
        os.close(write_fd)
        write_fd = None

        def receive():
            try:
                with os.fdopen(read_fd, 'rb', buffering=0) as stream:
                    while not stop.is_set():
                        magic, w, h = struct.unpack('<III', read_exact(stream, 12))
                        if magic != 0x43554245 or not (0 < w <= 4096 and 0 < h <= 4096):
                            raise ValueError('Invalid depth header')
                        depth = np.frombuffer(read_exact(stream, w*h*2), dtype='<u2').reshape(h, w)
                        with guard:
                            latest[:] = [depth, latest[1]+1, time.monotonic()]
            except Exception as error:
                errors.append(str(error))

        threading.Thread(target=receive, daemon=True).start()
        print(f'ToF depth preview -> {args.destination}:{args.port}/UDP; Ctrl+C to stop', flush=True)
        began = time.monotonic()
        shown = sent = 0
        next_frame = last_report = began
        while not stop.is_set():
            if errors or capture.poll() is not None:
                raise RuntimeError(f'Capture failed: {errors}; inspect SDK messages above')
            with guard:
                depth, count, stamp = latest
            now = time.monotonic()
            if depth is None:
                if now-began > 20:
                    raise RuntimeError('No depth frames for 20 seconds')
                stop.wait(.02)
                continue
            if now-stamp > 3:
                raise RuntimeError('Depth capture stalled for 3 seconds')
            if now < next_frame or shown == count:
                stop.wait(.005)
                continue
            h, w = depth.shape
            if encoder is None:
                shape = depth.shape
                encoder = subprocess.Popen([
                    'ffmpeg', '-hide_banner', '-loglevel', 'warning', '-nostdin',
                    '-f', 'rawvideo', '-pixel_format', 'bgr24', '-video_size', f'{w}x{h}',
                    '-framerate', str(args.fps), '-i', 'pipe:0', '-an',
                    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264',
                    '-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '1',
                    '-pix_fmt', 'yuv420p', '-b:v', f'{args.bitrate}k',
                    '-g', str(args.fps), '-bf', '0', '-x264-params', 'repeat-headers=1',
                    '-f', 'mpegts', '-flush_packets', '1',
                    f'udp://{args.destination}:{args.port}?pkt_size=1316'], stdin=subprocess.PIPE)
                os.set_blocking(encoder.stdin.fileno(), False)
            if depth.shape != shape:
                raise RuntimeError('Camera dimensions changed; restart stream')
            remaining = memoryview(preview(depth, args.max_depth).tobytes())
            deadline = time.monotonic()+3
            while remaining and not stop.is_set():
                if encoder.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Video encoder exited or stalled')
                if select.select([], [encoder.stdin], [], .1)[1]:
                    try:
                        remaining = remaining[os.write(encoder.stdin.fileno(), remaining):]
                    except BlockingIOError:
                        pass
            shown = count
            sent += 1
            next_frame = time.monotonic()+1/args.fps
            if now-last_report >= 2:
                print(f'capture={count} sent={sent} size={w}x{h} age_ms={(now-stamp)*1000:.0f}', flush=True)
                last_report = now
    finally:
        stop.set()
        if write_fd is not None:
            os.close(write_fd)
        for child in (encoder, capture):
            if child is not None:
                if child.poll() is None:
                    child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        if encoder is not None:
            encoder.stdin.close()
        if capture is None:
            os.close(read_fd)
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
