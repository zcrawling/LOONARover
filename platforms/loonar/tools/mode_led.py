#!/usr/bin/env python3
"""Pi-owned mode LEDs. Consumes telemetry only; never sends a vehicle command."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import select
import signal
import socket
import struct
import sys
import time

from neopixel import Pixels, byte, diagnostics

WHITE, BLUE, YELLOW, GREEN, RED, BLACK = (
    (255,255,255), (0,0,255), (255,255,0), (0,255,0), (255,0,0), (0,0,0))
MODES = {1:'AUTO', 2:'MANUAL', 3:'STOP', 4:'PAYLOAD', 5:'REACTION'}
CREDENTIALS = struct.Struct('3i')


def fresh(value, now, ttl):
    stamp = value.get('updated_mono')
    return (type(stamp) in (int,float) and math.isfinite(stamp) and
            -.02 <= now-stamp <= ttl)


def valid_status(value, now):
    return (isinstance(value, dict) and value.get('schema') == 1 and
            type(value.get('mode')) is int and value['mode'] in MODES and
            type(value.get('gcs_connected')) is bool and
            type(value.get('explicit_stop', False)) is bool and fresh(value, now, 1.))


def pattern(status, payloads, now, boot_id):
    if not valid_status(status, now) or not status['gcs_connected']:
        return 'IDLE', WHITE, 'steady'
    if status.get('mode_fresh', True) is not True:
        return 'IDLE', WHITE, 'steady'
    if status['mode'] == 5:
        return 'REACTION', RED, 'chase'
    if status['mode'] == 3 and status.get('explicit_stop', False):
        return 'STOP', RED, 'steady'
    active = any(isinstance(p, dict) and p.get('boot_id') == boot_id and
                 fresh(p, now, 3.) and p.get('online') is True and
                 p.get('sequence_active') is True for p in payloads)
    if active:
        return 'PAYLOAD', GREEN, 'blink'
    if status['mode'] == 2:
        return 'MANUAL', BLUE, 'steady'
    if status['mode'] == 1:
        return 'AUTO', YELLOW, 'steady'
    # PAYLOAD mode may remain selected after DONE/error. Only actual live
    # MCU activity blinks green; selected mode alone is not a running sequence.
    return 'IDLE', WHITE, 'steady'


def blink_rgb(rgb, blinking, elapsed, hz):
    return BLACK if blinking and int(max(0., elapsed)*hz*2) % 2 else rgb


def render_frame(selected, count, elapsed, blink_hz=2., chase_step=.1, reverse=False):
    _, rgb, animation = selected
    if animation == 'chase':
        head = int(max(0., elapsed)/chase_step)
        direction = -1 if reverse else 1
        lit = {(direction*(head+i)) % count for i in range(min(2,count))}
        return tuple(rgb if i in lit else BLACK for i in range(count))
    return (blink_rgb(rgb, animation == 'blink', elapsed, blink_hz),)*count


def read_payloads(paths):
    result = []
    for path in paths:
        try:
            if path.stat().st_size <= 8192:
                result.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
    return result


def run(args, pixels):
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    args.socket.parent.mkdir(parents=True, exist_ok=True)
    args.socket.unlink(missing_ok=True)
    status, selected, began, last_frame = {}, None, time.monotonic(), None
    last_report = 0.
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    sock.bind(str(args.socket))
    args.socket.chmod(0o660)
    sock.setblocking(False)
    try:
        while True:
            if select.select([sock], [], [], .04)[0]:
                for _ in range(32):
                    try:
                        data, ancillary, flags, _ = sock.recvmsg(1024, socket.CMSG_SPACE(CREDENTIALS.size))
                    except BlockingIOError:
                        break
                    uid = None
                    for level, kind, raw in ancillary:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                            _, uid, _ = CREDENTIALS.unpack(raw[:CREDENTIALS.size])
                    if uid not in (0, os.getuid()) or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                        continue
                    try:
                        candidate = json.loads(data)
                    except (ValueError, UnicodeError):
                        continue
                    if valid_status(candidate, time.monotonic()):
                        status = candidate
            now = time.monotonic()
            current = pattern(status, read_payloads(args.payload_status), now, boot_id)
            if current != selected:
                selected, began = current, now
                print(f'LED {selected[0]} animation={selected[2]}', flush=True)
            frame = render_frame(selected, args.count, now-began, args.blink_hz,
                                 args.chase_step, args.reverse)
            if frame != last_frame:
                pixels.write_frame(frame)
                last_frame = frame
            if now-last_report >= .2:
                payload = dict(updated_mono=now, boot_id=boot_id, indication=selected[0],
                    pixels=frame, brightness_255=args.brightness, animation=selected[2],
                    gcs_connected=bool(valid_status(status, now) and status['gcs_connected']),
                    mode=MODES.get(status.get('mode')) if valid_status(status, now) else None)
                temporary = args.socket.parent/'status.tmp'
                temporary.write_text(json.dumps(payload)+'\n')
                temporary.replace(args.socket.parent/'status.json')
                last_report = now
    finally:
        sock.close()
        args.socket.unlink(missing_ok=True)
        pixels.write(WHITE)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket', type=Path, default=Path('/run/loonar-led/status.sock'))
    p.add_argument('--gpio', type=int, default=22, choices=range(28))
    p.add_argument('--count', type=int, default=16)
    p.add_argument('--brightness', type=byte, default=30)
    p.add_argument('--blink-hz', type=float, default=2.)
    p.add_argument('--chase-step', type=float, default=.1, help='Seconds per reaction-wheel LED step')
    p.add_argument('--reverse', action='store_true', default=os.getenv('LOONAR_LED_REVERSE', '0') == '1',
                   help='Reverse index order if the installed ring is wired counterclockwise')
    p.add_argument('--payload-status', type=Path, action='append')
    args = p.parse_args()
    if (not 1 <= args.count <= 4096 or not math.isfinite(args.blink_hz) or not 0 < args.blink_hz <= 10
            or not math.isfinite(args.chase_step) or args.chase_step < .04):
        p.error('count must be 1..4096; 0<blink-hz<=10; chase-step must be finite, >=.04s')
    venv = Path.home()/'.venvs/loonar-neopixel'
    if (importlib.util.find_spec('adafruit_raspberry_pi5_neopixel_write') is None and
            sys.prefix != str(venv) and (venv/'bin/python').is_file()):
        os.execv(str(venv/'bin/python'), [str(venv/'bin/python'), str(Path(__file__).resolve()), *sys.argv[1:]])
    info = diagnostics()
    if info['errors']:
        raise RuntimeError('; '.join(info['errors']))
    args.payload_status = args.payload_status or [
        Path(f'/tmp/loonar-monitor-{os.getuid()}/payload.json'), Path('/tmp/loonar-monitor-0/payload.json')]
    def interrupted(*_):
        raise KeyboardInterrupt
    old = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    pixels = Pixels(args.gpio, args.count, args.brightness)
    try:
        run(args, pixels)
    except KeyboardInterrupt:
        pass
    finally:
        for sig in old:
            signal.signal(sig, signal.SIG_IGN)
        pixels.close()


if __name__ == '__main__':
    main()
