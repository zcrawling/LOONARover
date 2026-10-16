"""Focused-terminal Xbox Series USB controller; shares the running real GCS backend."""
from motion_limits import MAX_LINEAR, MAX_ANGULAR, TRACK_M, normalize_motion
import argparse
import fcntl
import json
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

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_DROPPED = 0, 3
LX, LY, LT, RX, RY, RT = range(6)
AXES = (LX, LY, LT, RX, RY, RT)
LB, RB = 0x136, 0x137  # Linux BTN_TL / BTN_TR.
X, Y = 0x133, 0x134  # Linux BTN_NORTH / BTN_WEST (xpad X / Y).
A, B = 0x130, 0x131  # Linux BTN_SOUTH / BTN_EAST.
BUTTONS = (LB, RB, X, Y, A, B)
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
            keys = read_ioctl(self.fd, 0x18, 40)  # EVIOCGKEY, includes BTN_TR.
            self.values.update({button: bool(keys[button // 8] & (1 << (button % 8)))
                                for button in BUTTONS})
            self.buffer = b''
            for axis in AXES:
                if self.info[axis][2] <= self.info[axis][1]:
                    raise ValueError('컨트롤러 축 범위 오류')
        except BaseException:
            os.close(self.fd)
            raise

    def normalized(self):
        result = {}
        for axis in AXES:
            raw = self.values[axis]
            low, high = self.info[axis][1:3]
            if axis in (LT, RT):
                result[axis] = max(0.0, min(1.0, (raw - low) / (high - low)))
            else:
                # xpad's signed axes are centered at zero, with asymmetric endpoints.
                result[axis] = max(-1.0, min(1.0, raw / (high if raw >= 0 else -low)))
        result.update({button: bool(self.values.get(button, 0)) for button in BUTTONS})
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
            if kind == EV_KEY and code in BUTTONS:
                self.values[code] = bool(value)
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


def stick(value, deadzone, maximum=1.0):
    if abs(value) <= deadzone:
        return 0.0
    magnitude = .01 + (maximum - .01) * (min(abs(value), 1.0) - deadzone) / (1.0 - deadzone)
    return math.copysign(magnitude, value)


class Controls:
    def __init__(self, initial, deadzone=.08):
        self.axes = dict(initial)
        self.deadzone = deadzone
        self.mode = 'A'
        self.manual = False
        self.focused = False
        self.down = {axis: initial.get(axis, 0) > .25 for axis in (LT, RT)}
        self.button_down = {button: bool(initial.get(button, 0)) for button in BUTTONS}
        self.k_steps = 5
        self.phase_deg = 180
        self.frequency_steps = 10
        self.wave_start = None

    @property
    def k(self):
        return self.k_steps / 10

    @property
    def f(self):
        return self.frequency_steps / 10

    def focus(self, value):
        stop = self.manual and not value
        self.focused = value
        if not value:
            self.manual = False
            self.wave_start = None
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
                        self.wave_start = None
                    else:
                        self.manual = not self.manual
                        actions.append('MANUAL' if self.manual else 'STOP')
        adjustment = 0
        phase_adjustment = 0
        frequency_adjustment = 0
        for button, step in ((LB, -1), (RB, 1), (X, -10), (Y, 10), (A, -1), (B, 1)):
            pressed = bool(axes.get(button, 0))
            if pressed and not self.button_down[button] and self.focused:
                if button in (LB, RB):
                    adjustment += step
                elif button in (X, Y):
                    phase_adjustment += step
                else:
                    frequency_adjustment += step
            self.button_down[button] = pressed
        self.k_steps = max(0, min(10, self.k_steps + adjustment))
        self.phase_deg = max(0, min(360, self.phase_deg + phase_adjustment))
        self.frequency_steps = max(0, min(20, self.frequency_steps + frequency_adjustment))
        if not self.manual or abs(axes[RY]) <= self.deadzone:
            self.wave_start = None
        return actions

    def motion(self, now=None):
        if not self.focused or not self.manual:
            self.wave_start = None
            return 0.0, 0.0
        linear = -stick(self.axes[LY], self.deadzone, maximum=MAX_LINEAR)
        if self.mode == 'A':
            angular = -stick(self.axes[RX], self.deadzone, maximum=MAX_ANGULAR)
            return (0.0, angular) if angular else (linear, 0.0)
        x = -stick(self.axes[RY], self.deadzone, maximum=MAX_LINEAR)
        if x:
            now = time.monotonic() if now is None else now
            if self.wave_start is None:
                self.wave_start = now
            phase = 2 * math.pi * self.f * (now - self.wave_start)
            left = x + self.k * x * math.sin(phase)
            right = x + self.k * x * math.sin(phase + math.radians(self.phase_deg % 360))
            # Scale wheels together before converting to the backend's v/w command.
            scale = max(1.0, abs(left) / MAX_LINEAR, abs(right) / MAX_LINEAR)
            return normalize_motion((left + right) / (2 * scale),
                                    (right - left) / (TRACK_M * scale))
        self.wave_start = None
        angular = -stick(self.axes[LX], self.deadzone, maximum=MAX_ANGULAR) if linear else 0.0
        return normalize_motion(linear, angular)


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
    def __init__(self, dry_run=False, event_log=None):
        self.dry_run = dry_run
        self.event_log = event_log
        self.active = False
        self.last = '대기'

    def send(self, command, motion=None):
        body = {'action': 'command', 'command': command}
        if motion is not None:
            body.update(linear_mps=motion[0], angular_radps=motion[1])
        # Mark before writing: an uncertain write still needs a best-effort STOP.
        if command == 'MANUAL':
            self.active = True
        issued_ns, issued_mono = time.time_ns(), time.monotonic_ns()
        def record(**fields):
            if self.event_log is not None:
                try:
                    self.event_log.write(json.dumps(dict(laptop_epoch_ns=issued_ns,
                        monotonic_ns=issued_mono, command=body, dry_run=self.dry_run, **fields))+'\n')
                    self.event_log.flush()
                except OSError as exc:
                    # Storage failure must never prevent the normal STOP path.
                    self.event_log = None
                    print(f'\r\n명령 로그 저장 실패: {safe(exc)}', file=sys.stderr)
        record(event='issued')
        result = {'ok': True, 'text': 'DRY RUN / 로버 전송 없음'} if self.dry_run else request(body, timeout=.5)
        record(event='response', response_epoch_ns=time.time_ns(), response=result)
        if not result.get('ok'):
            raise RuntimeError(result.get('text', '명령 전송 실패'))
        if command == 'STOP':
            self.active = False
        self.last = result.get('text', command)

    def stop(self):
        if self.active:
            self.send('STOP')


def render(device, controls, output, rover, now=None):
    v, w = controls.motion(now)
    lines = [f'XBOX | 주행모드: {controls.mode} | 조종: {"MANUAL" if controls.manual else "STOP"} | k={controls.k:.1f} | c={controls.phase_deg}° | f={controls.f:.1f}Hz',
             f'터미널 포커스: {"ON" if controls.focused else "OFF / 다른 창으로 전환 후 돌아오세요"}',
             f'로버 상태: {rover}', f'선속도 {v:+.3f} m/s | 각속도 {w:+.3f} rad/s',
             'LT: A/B 전환  RT: STOP/MANUAL 전환  Q/Ctrl+C: 정지 후 종료',
             'A: 왼쪽 전후 직진 / 오른쪽 좌우 제자리 회전 (회전 우선)',
             'B: 왼쪽 전후 + 좌우 조향 / 오른쪽 상하: f Hz 좌우 속도 변조 (우선)',
             'LB: k -0.1 / RB: k +0.1 (0~1, 기본 0.5)',
             'X: c -10° / Y: c +10° (0~360°, 기본 180°)',
             'A 버튼: f -0.1Hz / B 버튼: f +0.1Hz (0~2Hz, 기본 1Hz)',
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
        event_log = None
        if getattr(args, 'event_log', None):
            args.event_log.parent.mkdir(parents=True, exist_ok=True)
            event_log = args.event_log.open('x')
        output = Output(args.dry_run, event_log)
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
                    output.send('MANUAL', controls.motion(now))
                    next_send = now + .1
                render(device, controls, output, rover, now)
        finally:
            # A second Ctrl+C during cleanup must not interrupt the STOP request.
            for sig in old_handlers:
                signal.signal(sig, signal.SIG_IGN)
            try:
                output.stop()
            except (OSError, ValueError, RuntimeError) as exc:
                print(f'\r\nSTOP 전달 확인 불가: {safe(exc)}', file=sys.stderr)
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)
            print('\x1b[?1004l\x1b[?25h\x1b[?1049l', end='', flush=True)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            device.close()
            if event_log is not None:
                event_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='자동 탐색 대신 /dev/input/eventN 지정')
    parser.add_argument('--deadzone', type=float, default=.08, help='스틱 중심 무입력 범위 (기본 0.08)')
    parser.add_argument('--dry-run', action='store_true', help='로버/백엔드 없이 입력과 속도 표시만')
    parser.add_argument('--inspect', action='store_true', help='장치/축 범위 확인만 하고 종료')
    parser.add_argument('--event-log', type=Path, help='세션 분석용 명령 시각/응답 JSONL (새 파일)')
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
