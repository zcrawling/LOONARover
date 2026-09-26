"""Focused-terminal Xbox Series USB controller; shares the running real GCS backend."""
import argparse
import fcntl
import math
import os
from pathlib import Path
import select
import signal
import struct
import sys
import termios
import time
import tty

from backend.config import LOCAL_SOCKET
from cli.common import request, safe

EV_SYN, EV_ABS = 0, 3
SYN_REPORT, SYN_DROPPED = 0, 3
LX, LY, LT, RX, RY, RT = range(6)
AXES = (LX, LY, LT, RX, RY, RT)
EVENT = struct.Struct('@llHHi')
ABSINFO = struct.Struct('@iiiiii')


def read_ioctl(fd, number, size):
    data = bytearray(size)
    fcntl.ioctl(fd, 0x80000000 | (size << 16) | (ord('E') << 8) | number, data, True)
    return data


class XboxDevice:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            _, vendor, product, _ = struct.unpack('@HHHH', read_ioctl(self.fd, 0x02, 8))
            if (vendor, product) != (0x045e, 0x0b12):
                raise ValueError(f'{path}: Xbox 045e:0b12 장치가 아닙니다')
            self.info = {axis: ABSINFO.unpack(read_ioctl(self.fd, 0x40 + axis, 24)) for axis in AXES}
            self.values = {axis: info[0] for axis, info in self.info.items()}
            self.buffer = b''
            for axis in AXES:
                if self.info[axis][2] <= self.info[axis][1]:
                    raise ValueError('컨트롤러 축 범위 오류')
        except BaseException:
            os.close(self.fd)
            raise

    def normalized(self):
        result = {}
        for axis, raw in self.values.items():
            low, high = self.info[axis][1:3]
            if axis in (LT, RT):
                result[axis] = max(0.0, min(1.0, (raw - low) / (high - low)))
            else:
                # xpad's signed axes are centered at zero, with asymmetric endpoints.
                result[axis] = max(-1.0, min(1.0, raw / (high if raw >= 0 else -low)))
        return result

    def reports(self):
        data = os.read(self.fd, EVENT.size * 64)
        if not data:
            raise OSError('컨트롤러 연결이 끊어졌습니다')
        self.buffer += data
        reports = []
        while len(self.buffer) >= EVENT.size:
            _, _, kind, code, value = EVENT.unpack_from(self.buffer)
            self.buffer = self.buffer[EVENT.size:]
            if kind == EV_SYN and code == SYN_DROPPED:
                # End the session rather than interpreting a partial trigger/axis history.
                raise OSError('컨트롤러 이벤트 유실: STOP 후 다시 실행하세요')
            if kind == EV_ABS and code in AXES:
                self.values[code] = value
            if kind == EV_SYN and code == SYN_REPORT:
                reports.append(self.normalized())
        return reports

    def close(self):
        os.close(self.fd)


def discover():
    matches = []
    for entry in sorted(Path('/sys/class/input').glob('event*')):
        ids = entry / 'device/id'
        try:
            if (int((ids / 'vendor').read_text(), 16),
                    int((ids / 'product').read_text(), 16)) == (0x045e, 0x0b12):
                matches.append('/dev/input/' + entry.name)
        except (OSError, ValueError):
            continue
    if len(matches) != 1:
        raise RuntimeError(f'Xbox 장치 {len(matches)}개 발견: --device /dev/input/eventN으로 지정하세요')
    return matches[0]


def stick(value, deadzone):
    if abs(value) <= deadzone:
        return 0.0
    magnitude = .01 + .99 * (min(abs(value), 1.0) - deadzone) / (1.0 - deadzone)
    return math.copysign(magnitude, value)


class Controls:
    def __init__(self, initial, deadzone=.08):
        self.axes = dict(initial)
        self.deadzone = deadzone
        self.mode = 'A'
        self.manual = False
        self.focused = False
        self.down = {axis: initial.get(axis, 0) > .25 for axis in (LT, RT)}

    def focus(self, value):
        stop = self.manual and not value
        self.focused = value
        if not value:
            self.manual = False
        return stop

    def update(self, axes):
        self.axes = dict(axes)
        actions = []
        for axis in (LT, RT):
            pressed = self.down[axis]
            if axes[axis] <= .25:
                self.down[axis] = False
            elif axes[axis] >= .65 and not pressed:
                self.down[axis] = True
                if self.focused:
                    if axis == LT:
                        self.mode = 'B' if self.mode == 'A' else 'A'
                    else:
                        self.manual = not self.manual
                        actions.append('MANUAL' if self.manual else 'STOP')
        return actions

    def motion(self):
        if not self.focused or not self.manual:
            return 0.0, 0.0
        linear = -stick(self.axes[LY], self.deadzone)
        if self.mode == 'A':
            angular = -stick(self.axes[RX], self.deadzone)
            return (0.0, angular) if angular else (linear, 0.0)
        angular = -stick(self.axes[LX], self.deadzone) if linear else 0.0
        return linear, angular


class TerminalInput:
    """Incremental focus-sequence parser; never enable control via ordinary keys."""
    def __init__(self):
        self.buffer = b''

    def feed(self, data):
        self.buffer += data
        events = []
        while self.buffer:
            if self.buffer.startswith(b'\x1b['):
                if len(self.buffer) < 3:
                    break
                code = self.buffer[2:3]
                if code in (b'I', b'O'):
                    events.append('in' if code == b'I' else 'out')
                    self.buffer = self.buffer[3:]
                    continue
            if self.buffer == b'\x1b':
                break
            if self.buffer[:1] in (b'q', b'Q', b'\x03'):
                events.append('quit')
            self.buffer = self.buffer[1:]
        return events


class Output:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.active = False
        self.last = '대기'

    def send(self, command, motion=None):
        body = {'action': 'command', 'command': command}
        if motion is not None:
            body.update(linear_mps=motion[0], angular_radps=motion[1])
        # Mark before writing: an uncertain write still needs a best-effort STOP.
        if command == 'MANUAL':
            self.active = True
        result = {'ok': True, 'text': 'DRY RUN / 로버 전송 없음'} if self.dry_run else request(body, timeout=.5)
        if not result.get('ok'):
            raise RuntimeError(result.get('text', '명령 전송 실패'))
        if command == 'STOP':
            self.active = False
        self.last = result.get('text', command)

    def stop(self):
        if self.active:
            self.send('STOP')


def render(device, controls, output, rover):
    v, w = controls.motion()
    lines = [f'XBOX | 주행모드: {controls.mode} | 조종: {"MANUAL" if controls.manual else "STOP"}',
             f'터미널 포커스: {"ON" if controls.focused else "OFF / 다른 창으로 전환 후 돌아오세요"}',
             f'로버 상태: {rover}', f'선속도 {v:+.3f} m/s | 각속도 {w:+.3f} rad/s',
             'LT: A/B 전환  RT: STOP/MANUAL 전환  Q/Ctrl+C: 정지 후 종료',
             'A: 왼쪽 전후 직진 / 오른쪽 좌우 제자리 회전 (회전 우선)',
             'B: 왼쪽 전후 + 좌우 조향 / 오른쪽 사용 안 함',
             '포커스 이탈·장치 분리 시 STOP. 복귀 후 RT로 MANUAL 재선택.',
             f'장치: {device.path}', f'전송: {output.last}']
    print('\x1b[H' + '\r\n'.join('\x1b[2K' + safe(line) for line in lines) + '\x1b[J', end='', flush=True)


def run(args):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError('별도 GNOME Terminal에서 실행하세요 (포커스 보고 필요)')
    if os.environ.get('TMUX') or os.environ.get('STY'):
        raise RuntimeError('tmux/screen 밖의 별도 GNOME Terminal에서 실행하세요')
    LOCAL_SOCKET.parent.mkdir(mode=0o700, exist_ok=True)
    with (LOCAL_SOCKET.parent / 'xbox.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Xbox 조종기가 이미 실행 중입니다') from None
        device = XboxDevice(args.device or discover())
        output = Output(args.dry_run)
        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        controls = Controls(device.normalized(), args.deadzone)
        inputs = TerminalInput()
        rover = 'DRY RUN' if args.dry_run else '연결 확인 중'
        old_handlers = {}
        def interrupted(_sig, _frame):
            raise KeyboardInterrupt
        try:
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                old_handlers[sig] = signal.signal(sig, interrupted)
            tty.setcbreak(fd)
            print('\x1b[?1049h\x1b[?25l\x1b[?1004h', end='', flush=True)
            next_send = next_state = 0.0
            while True:
                readable, _, _ = select.select([fd, device.fd], [], [], .05)
                # Handle focus loss before processing controller reports in the same cycle.
                if fd in readable:
                    data = os.read(fd, 1024)
                    if not data:
                        return
                    for event in inputs.feed(data):
                        if event == 'quit':
                            return
                        if controls.focus(event == 'in'):
                            output.stop()
                if device.fd in readable:
                    for axes in device.reports():
                        for action in controls.update(axes):
                            output.send(action, (0.0, 0.0) if action == 'MANUAL' else None)
                now = time.monotonic()
                if not args.dry_run and now >= next_state:
                    state = request({'action': 'state'}, timeout=.5)
                    if not str(state.get('source', '')).startswith('REAL ROVER / '):
                        raise RuntimeError('실제 GroundLink 백엔드가 필요합니다. 장치만 테스트하려면 --dry-run')
                    rover = f'{state.get("connection")} / {state.get("status", {}).get("mode", "—")}'
                    if state.get('connection') != 'CONNECTED':
                        controls.manual = False
                        # No queued motion is replayed after reconnect.
                        output.stop()
                    next_state = now + .5
                if controls.focused and controls.manual and now >= next_send:
                    output.send('MANUAL', controls.motion())
                    next_send = now + .1
                render(device, controls, output, rover)
        finally:
            try:
                output.stop()
            except (OSError, ValueError, RuntimeError) as exc:
                print(f'\r\nSTOP 전달 확인 불가: {safe(exc)}', file=sys.stderr)
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)
            print('\x1b[?1004l\x1b[?25h\x1b[?1049l', end='', flush=True)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='자동 탐색 대신 /dev/input/eventN 지정')
    parser.add_argument('--deadzone', type=float, default=.08, help='스틱 중심 무입력 범위 (기본 0.08)')
    parser.add_argument('--dry-run', action='store_true', help='로버/백엔드 없이 입력과 속도 표시만')
    parser.add_argument('--inspect', action='store_true', help='장치/축 범위 확인만 하고 종료')
    args = parser.parse_args()
    if not 0 <= args.deadzone < 1:
        parser.error('--deadzone은 0 이상 1 미만이어야 합니다')
    try:
        if args.inspect:
            device = XboxDevice(args.device or discover())
            try:
                print(f'Xbox Series USB 045e:0b12: {device.path}')
                for axis, name in zip(AXES, ('LX', 'LY', 'LT', 'RX', 'RY', 'RT')):
                    print(f'{name}: value/min/max={device.info[axis][:3]}')
            finally:
                device.close()
            return
        run(args)
    except KeyboardInterrupt:
        print('Xbox 조종 종료 (활성 상태였다면 STOP 전송 시도).')
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Xbox 조종기 오류: {exc}\n')


if __name__ == '__main__':
    main()
