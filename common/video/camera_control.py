"""Local, acknowledged exposure control for the process owning libcamerasrc."""
import fcntl
import json
import math
import os
from pathlib import Path
import socket


def socket_path():
    return Path.home()/'.cache/loonar/camera-control.sock'


class Exposure:
    def __init__(self, source):
        self.source = source
        self.ev = 0.0
        self.profile = 'auto'
        self.configured = False

    def handle(self, request):
        if not isinstance(request, dict):
            raise ValueError('잘못된 카메라 명령')
        operation = request.get('operation')
        if operation not in ('status', 'set', 'add', 'auto', 'backlight'):
            raise ValueError('지원하지 않는 노출 명령')
        if self.source is None:
            raise ValueError('실행 중인 카메라가 libcamerasrc가 아닙니다')
        if operation != 'status':
            ev, profile = self.ev, self.profile
            if operation in ('set', 'add'):
                value = request.get('value')
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError('EV는 유한한 숫자여야 합니다')
                ev = value if operation == 'set' else self.ev + value
            else:
                ev = 1.0 if operation == 'backlight' else 0.0
                profile = operation
            if not -3 <= ev <= 3:
                raise ValueError('노출 보정 범위는 -3~+3 EV입니다')
            controls = {'ae-enable': True, 'exposure-value': float(ev),
                        'ae-metering-mode': 0,
                        'ae-constraint-mode': 2 if profile == 'backlight' else 0}
            for name in controls:
                if self.source.find_property(name) is None:
                    raise ValueError(f'설치된 카메라 플러그인이 {name} 제어를 지원하지 않습니다')
            for name, value in controls.items():
                self.source.set_property(name, value)
            self.ev, self.profile, self.configured = float(ev), profile, True
        return {'ok': True, 'ev': self.ev, 'profile': self.profile,
                'configured': self.configured,
                'text': (f'노출 설정 EV {self.ev:+.1f} / '
                         f'{"역광·어두운 영역 우선" if self.profile == "backlight" else "자동 노출·중앙 측광"}'
                         + ('' if self.configured else ' (아직 조절하지 않음)'))}


class ControlServer:
    def __init__(self, source, path=None):
        self.path = Path(path) if path else socket_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = self.path.with_suffix('.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('Another camera control owner is running')
        self.path.unlink(missing_ok=True)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.sock.setblocking(False)
        self.exposure = Exposure(source)

    def poll(self):
        # Bounded work; malformed clients must not stall video processing.
        for _ in range(8):
            try:
                raw, peer = self.sock.recvfrom(4097)
            except BlockingIOError:
                return
            try:
                if len(raw) > 4096:
                    raise ValueError('카메라 명령 크기 초과')
                result = self.exposure.handle(json.loads(raw))
            except (ValueError, TypeError, OverflowError, RuntimeError) as error:
                result = {'ok': False, 'text': str(error)}
            if peer:
                try:
                    self.sock.sendto(json.dumps(result, ensure_ascii=False).encode(), peer)
                except OSError:
                    pass  # A disconnected SSH requester must not stop the camera.

    def close(self):
        self.sock.close()
        self.path.unlink(missing_ok=True)
        self.lock.close()
