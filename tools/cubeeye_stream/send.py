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


def read_exact(stream, size, stop, deadline):
    """Read a packet with a deadline, including a partially received header/body."""
    data = bytearray()
    while len(data) < size:
        if stop.is_set():
            raise InterruptedError('Stopping capture')
        if time.monotonic() >= deadline:
            raise TimeoutError('No complete depth frame before timeout')
        if not select.select([stream], [], [], .1)[0]:
            continue
        part = os.read(stream, size - len(data))
        if not part:
            raise EOFError('CubeEye capture ended')
        data.extend(part)
    return data


def stop_child(child):
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def rotate_depth(depth, rotation):
    # Mount TF: raw pixel-right is robot-up. CCW maps it to display-up.
    return np.rot90(depth, {'left': 1, 'right': -1, '180': 2, 'none': 0}[rotation])


def preview(depth, maximum, rotation='left', status=None):
    depth = rotate_depth(depth, rotation)
    valid = (depth > 0) & (depth < 65535)
    gray = (np.clip(depth.astype(np.float32) / maximum, 0, 1) * 255).astype(np.uint8)
    color = cv2.applyColorMap(255 - gray, cv2.COLORMAP_TURBO)
    color[~valid] = 0
    cv2.putText(color, f'Depth: 0..{maximum} raw | valid {valid.mean()*100:.0f}%',
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
    if status:
        cv2.rectangle(color, (0, 30), (color.shape[1], 62), (0, 0, 130), -1)
        cv2.putText(color, status, (8, 52), cv2.FONT_HERSHEY_SIMPLEX,
                    .5, (255, 255, 255), 1)
    return color


class Capture:
    """Keep only the newest frame; retry SDK failures without stopping video."""

    def __init__(self, helper, env, stop, frame_timeout, retry_delay):
        self.helper, self.env, self.stop = helper, env, stop
        self.frame_timeout, self.retry_delay = frame_timeout, retry_delay
        self.lock = threading.Lock()
        self.latest = (None, 0, 0.0)
        self.thread = threading.Thread(target=self.run, daemon=True)

    def snapshot(self):
        with self.lock:
            return self.latest

    def run(self):
        while not self.stop.is_set():
            child = None
            read_fd, write_fd = os.pipe()
            try:
                child = subprocess.Popen([str(self.helper), str(write_fd)],
                                         pass_fds=(write_fd,), env=self.env)
                os.close(write_fd)
                write_fd = None
                # Initial sensor setup may take longer than an ordinary frame.
                deadline = time.monotonic() + max(20, self.frame_timeout)
                while not self.stop.is_set():
                    magic, w, h = struct.unpack('<III', read_exact(read_fd, 12, self.stop, deadline))
                    if magic != 0x43554245 or not (0 < w <= 4096 and 0 < h <= 4096):
                        raise ValueError('Invalid depth header')
                    raw = read_exact(read_fd, w*h*2, self.stop, deadline)
                    depth = np.frombuffer(raw, dtype='<u2').reshape(h, w)
                    with self.lock:
                        self.latest = (depth, self.latest[1]+1, time.monotonic())
                    deadline = time.monotonic() + self.frame_timeout
            except (OSError, EOFError, ValueError, TimeoutError) as error:
                if not self.stop.is_set():
                    print(f'ToF unavailable: {error}; reconnect in {self.retry_delay:g}s', flush=True)
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
                if child is not None:
                    stop_child(child)
            self.stop.wait(self.retry_delay)


def start_encoder(args, shape):
    h, w = shape[:2]
    child = subprocess.Popen([
        'ffmpeg', '-hide_banner', '-loglevel', 'warning', '-nostdin',
        '-probesize', '32', '-analyzeduration', '1', '-fpsprobesize', '0',
        '-use_wallclock_as_timestamps', '1',
        '-f', 'rawvideo', '-pixel_format', 'bgr24', '-video_size', f'{w}x{h}',
        '-framerate', str(args.fps), '-i', 'pipe:0', '-an',
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '1',
        '-pix_fmt', 'yuv420p', '-b:v', f'{args.bitrate}k',
        '-maxrate', f'{args.bitrate}k', '-bufsize', f'{max(64, args.bitrate*2//args.fps)}k',
        '-g', str(max(1, args.fps//2)), '-bf', '0',
        '-x264-params', 'repeat-headers=1:scenecut=0:rc-lookahead=0:sync-lookahead=0',
        '-fps_mode', 'vfr', '-f', 'mpegts',
        '-omit_video_pes_length', '0',
        '-muxdelay', '0', '-muxpreload', '0', '-flush_packets', '1',
        f'udp://{args.destination}:{args.port}?pkt_size=1316'], stdin=subprocess.PIPE)
    os.set_blocking(child.stdin.fileno(), False)
    return child


def write_frame(encoder, frame, stop):
    remaining = memoryview(frame.tobytes())
    # Never sit on an old partially written frame for seconds. Restarting the
    # encoder is required after a partial write to preserve raw-frame alignment.
    deadline = time.monotonic() + .3
    while remaining and not stop.is_set():
        if encoder.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Video encoder exited or stalled')
        if select.select([], [encoder.stdin], [], .1)[1]:
            try:
                remaining = remaining[os.write(encoder.stdin.fileno(), remaining):]
            except BlockingIOError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', nargs='?', default='10.254.25.3')
    parser.add_argument('--port', type=int, default=5602)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--bitrate', type=int, default=1000, help='H.264 kbit/s')
    parser.add_argument('--max-depth', type=int, default=3000, help='SDK native depth units')
    parser.add_argument('--rotate', choices=('left', 'right', '180', 'none'), default='left',
                        help='Mount correction; default: 90 degrees counterclockwise')
    parser.add_argument('--frame-timeout', type=float, default=10,
                        help='Restart capture after this many seconds without a complete frame')
    parser.add_argument('--retry-delay', type=float, default=2, help='Seconds between capture retries')
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get(
        'LOONAR_CUBEEYE_SDK', '/opt/loonar/vendor/cubeeye/2.5.9/release')))
    parser.add_argument('--helper', type=Path, help='Use an already compiled capture helper')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    try:
        ipaddress.IPv4Address(args.destination)
    except ValueError:
        parser.error('destination must be an IPv4 address')
    if not (1 <= args.port <= 65535 and 1 <= args.fps <= 30
            and 1 <= args.bitrate <= 20000 and 1 <= args.max_depth <= 65534
            and .5 <= args.frame_timeout <= 300 and .1 <= args.retry_delay <= 60):
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
    capture = Capture(helper.resolve(), env, stop, args.frame_timeout, args.retry_delay)
    encoder = None
    capture.thread.start()
    print(f'ToF monitor -> {args.destination}:{args.port}/UDP; rotation={args.rotate}; Ctrl+C to stop', flush=True)
    placeholder = np.zeros((480, 640), dtype=np.uint16)
    sent = 0
    next_frame = last_report = time.monotonic()
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now < next_frame:
                stop.wait(min(.05, next_frame-now))
                continue
            depth, count, stamp = capture.snapshot()
            if depth is None:
                frame = preview(placeholder, args.max_depth, args.rotate, 'WAITING FOR TOF / reconnecting')
            else:
                status = f'STALE {now-stamp:.1f}s / waiting for ToF' if now-stamp > 1 else None
                frame = preview(depth, args.max_depth, args.rotate, status)
            try:
                if encoder is not None and frame.shape != shape:
                    stop_child(encoder)
                    encoder.stdin.close()
                    encoder = None
                if encoder is None:
                    shape = frame.shape
                    encoder = start_encoder(args, shape)
                write_frame(encoder, frame, stop)
                sent += 1
            except (OSError, RuntimeError) as error:
                print(f'Video unavailable: {error}; restarting encoder', flush=True)
                if encoder is not None:
                    stop_child(encoder)
                    encoder.stdin.close()
                    encoder = None
                stop.wait(args.retry_delay)
            next_frame = max(next_frame + 1/args.fps, time.monotonic())
            if now-last_report >= 2:
                age = f'{(now-stamp)*1000:.0f}ms' if stamp else 'no frame'
                print(f'capture={count} sent={sent} age={age}', flush=True)
                last_report = now
    finally:
        stop.set()
        if encoder is not None:
            stop_child(encoder)
            encoder.stdin.close()
        capture.thread.join(timeout=5)
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
