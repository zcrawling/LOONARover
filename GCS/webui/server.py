import argparse
import json
import secrets
import signal
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.config import ROOT, DEFAULT_CONFIG, load
from cli.common import request

STATIC = Path(__file__).parent / 'static'
COMMANDS = {'STOP', 'MANUAL', 'AUTO', 'PAYLOAD', 'REACTION',
            'FORWARD', 'LEFT', 'REVERSE', 'RIGHT'}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Invalid host'})
        path = urlparse(self.path).path
        if path == '/api/state':
            try:
                state = request({'action': 'state'})
                state['csrf_token'] = self.server.token
                return self.reply(200, state)
            except (OSError, ValueError):
                return self.reply(503, {'error': '백엔드에 연결할 수 없습니다.'})
        assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
        if path not in assets:
            return self.reply(404, {'error': 'Not found'})
        name, mime = assets[path]
        return self.reply(200, (STATIC/name).read_bytes(), mime)

    def do_POST(self):
        origin = self.headers.get('Origin')
        valid_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if not self.allowed() or origin not in valid_origins or not secrets.compare_digest(self.headers.get('X-GCS-Token', ''), self.server.token):
            return self.reply(403, {'error': 'Invalid origin or session token'})
        if self.path != '/api/command':
            return self.reply(404, {'error': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('Invalid length')
            self.connection.settimeout(3)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or body.get('command') not in COMMANDS:
                raise ValueError('지원하지 않는 명령입니다.')
            speed = body.get('linear_speed_mps')
            if speed is not None and (type(speed) not in (int, float) or not 0.01 <= speed <= 1.0):
                raise ValueError('선속도 범위 오류')
            angular = body.get('angular_speed_radps')
            if angular is not None and (type(angular) not in (int, float) or not 0.01 <= angular <= 1.0):
                raise ValueError('각속도 범위 오류')
        except (ValueError, OSError, TypeError):
            return self.reply(400, {'error': '명령 형식이 올바르지 않습니다.'})
        try:
            local_request = {'action': 'command', 'command': body['command']}
            if body.get('linear_speed_mps') is not None:
                local_request['linear_speed_mps'] = body['linear_speed_mps']
            if body.get('angular_speed_radps') is not None:
                local_request['angular_speed_radps'] = body['angular_speed_radps']
            result = request(local_request)
            return self.reply(200, result)
        except (OSError, ValueError):
            return self.reply(502, {'error': '명령 결과 확인 불가 — 자동 재전송하지 않습니다.'})


def reachable(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def start_services(config_path, children, log, real_host=None):
    if real_host:
        env = dict(__import__('os').environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        child = subprocess.Popen([sys.executable, '-B', '-m', 'backend.real_app', '--host', real_host,
                                  '--config', str(config_path)], cwd=ROOT, env=env, stdout=log,
                                 stderr=log, start_new_session=True)
        children.append(child)
        # Give this child time to acquire the single-backend lock. Without this,
        # a stale backend can answer the first probe before the new child exits.
        time.sleep(0.2)
        deadline = time.monotonic()+7
        while True:
            if child.poll() is not None:
                raise RuntimeError('실제 백엔드 실행 실패. 이전 지상국 백엔드가 남아 있는지 확인하세요.')
            try:
                request({'action': 'state'})
                return
            except (OSError, ValueError):
                if time.monotonic()>deadline:
                    raise RuntimeError('실제 백엔드 실행 실패. webui/runtime/services.log를 확인하세요.')
                time.sleep(0.1)
    c = load(config_path)
    try:
        request({'action': 'state'})
        print('실행 중인 GCS 백엔드를 연결합니다.', flush=True)
        return
    except (OSError, ValueError):
        pass
    env = dict(__import__('os').environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    if not reachable(c['network']['host'], c['network']['port']):
        child = subprocess.Popen([sys.executable, '-B', '-m', 'mock.rover', '--config', str(config_path)], cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True)
        children.append(child)
        deadline = time.monotonic()+5
        while not reachable(c['network']['host'], c['network']['port']):
            if child.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Mock 실행 실패. webui/runtime/services.log를 확인하세요.')
            time.sleep(0.1)
    child = subprocess.Popen([sys.executable, '-B', '-m', 'backend.app', '--config', str(config_path)], cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True)
    children.append(child)
    deadline = time.monotonic()+7
    while True:
        try:
            request({'action': 'state'})
            return
        except (OSError, ValueError):
            if child.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('백엔드 실행 실패. webui/runtime/services.log를 확인하세요.')
            time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--attach', action='store_true', help='Run UI only; use existing backend')
    parser.add_argument('--real-host', help='Mock 대신 실제 GroundLink 로버 IP에 연결')
    args = parser.parse_args()
    runtime = Path(__file__).parent / 'runtime'
    runtime.mkdir(exist_ok=True)
    children = []
    server = None
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        # Bind before starting child processes so a second launcher is harmless.
        server = Server(('127.0.0.1', args.port))
        with open(runtime/'services.log', 'a') as log:
            if not args.attach:
                start_services(Path(args.config).resolve(), children, log, args.real_host)
            print(f'LOONAR GCS: http://127.0.0.1:{server.server_port}', flush=True)
            print('브라우저에서 위 주소를 여세요. 종료: Ctrl+C (새로 시작한 프로세스만 종료)', flush=True)
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'시작 실패: {exc}', file=sys.stderr)
        return 1
    finally:
        if server:
            server.server_close()
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    return 0


if __name__ == '__main__':
    sys.exit(main())
