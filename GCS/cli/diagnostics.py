"""Separate read-only terminal dashboard; no second GroundLink connection."""
import argparse
import concurrent.futures
import fcntl
import json
import math
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from backend.config import ROOT, DEFAULT_CONFIG
from cli.common import request, safe

ORDER = ('NETWORK', 'SSH PORT', 'SSH LOGIN', 'GROUNDLINK', 'DATA RECEIVED',
         'ROVER DRIVER', 'ROS BACKEND', 'GATEWAY', 'COMMAND')
REMOTE = r'''source /opt/ros/humble/setup.bash >/dev/null 2>&1
source "$HOME/agilex_ws/install/setup.bash" >/dev/null 2>&1
for item in 'DRIVER|/[l]imo_base/lib/limo_base/limo_base' 'BACKEND|/[l]oonar_limo_backend/lib/loonar_limo_backend' 'GATEWAY|/[v]ehicle_gatewayd( |$)'; do
 name=${item%%|*}; pattern=${item#*|}
 if pgrep -u "$USER" -f "$pattern" >/dev/null; then echo "$name=RUNNING"; else echo "$name=MISSING"; fi
done
if timeout 3 ros2 topic echo /limo_status --once >/dev/null 2>&1; then echo DATA=OK; else echo DATA=TIMEOUT; fi
'''


def timestamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime('%H:%M:%S')
    except (TypeError, ValueError):
        return '—'


def probe(host, target, control):
    rows = {}
    try:
        p = subprocess.run(['ping', '-c', '1', '-W', '1', host], capture_output=True, timeout=2)
        rows['NETWORK'] = ('정상', '로버 ping 응답') if p.returncode == 0 else ('확인 불가', 'ping 응답 없음 · ICMP 차단 가능')
    except (OSError, subprocess.TimeoutExpired):
        rows['NETWORK'] = ('확인 불가', 'ping 검사 실패')
    try:
        with socket.create_connection((host, 22), timeout=2):
            pass
        rows['SSH PORT'] = ('정상', 'TCP 22 열림')
    except OSError as e:
        rows['SSH PORT'] = ('실패', safe(e))
    if not target:
        rows['SSH LOGIN'] = ('확인 불가', '저장된 SSH 계정 없음 · --target user@host 지정')
    else:
        args = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                '-o', 'StrictHostKeyChecking=yes']
        if control:
            args += ['-S', str(control)]
        try:
            p = subprocess.run(args + [target, 'bash -c ' + shlex.quote(REMOTE)],
                               capture_output=True, text=True, timeout=12)
            if p.returncode != 0:
                rows['SSH LOGIN'] = ('실패', safe(p.stderr.strip()) or 'SSH 검사 실패')
            else:
                rows['SSH LOGIN'] = ('정상', '인증 및 원격 조회 성공')
                values = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
                for name, key in [('ROVER DRIVER', 'DRIVER'), ('ROS BACKEND', 'BACKEND'), ('GATEWAY', 'GATEWAY')]:
                    value = values.get(key)
                    rows[name] = ('정상', '프로세스 실행 중') if value == 'RUNNING' else ('실패', '프로세스 없음') if value == 'MISSING' else ('확인 불가', '검사 결과 없음')
                if values.get('DRIVER') == 'RUNNING':
                    rows['ROVER DRIVER'] = ('정상', 'limo_base 실행 · /limo_status 수신') if values.get('DATA') == 'OK' else ('지연', 'limo_base 실행 · 3초 동안 상태 수신 없음')
        except (OSError, subprocess.TimeoutExpired) as e:
            rows['SSH LOGIN'] = ('실패', safe(e))
    for name in ('ROVER DRIVER', 'ROS BACKEND', 'GATEWAY'):
        rows.setdefault(name, ('확인 불가', 'SSH로 내부 상태를 검사하지 못함'))
    return {name: (status, detail, timestamp()) for name, (status, detail) in rows.items()}


def backend_rows(host):
    state = request({'action': 'state'})
    if state.get('source') != 'REAL ROVER / ' + host:
        raise ValueError('백엔드가 다른 로버 또는 Mock 모드입니다.')
    checked = timestamp()
    connected = state.get('connection') == 'CONNECTED'
    rows = {'GROUNDLINK': ('연결됨' if connected else '끊김',
                           state.get('error') or 'GCS의 실제 TCP 연결', checked)}
    age = state.get('last_rx_age')
    rows['DATA RECEIVED'] = (age, connected, state.get('rx_messages', 0))
    requests = state.get('requests', [])
    if requests:
        last = requests[-1]
        result = last.get('state')
        event = next((e for e in reversed(state.get('events', []))
                      if str(e.get('request_id')) == str(last.get('request_id'))), {})
        rows['COMMAND'] = ('처리 완료' if result == 'Completed' else '처리 중' if result == 'Pending' else '확인 불가',
                           f'{last.get("command")} #{last.get("request_id")} · {result}',
                           event.get('time') or checked)
    else:
        rows['COMMAND'] = ('대기', '송신한 명령 없음', checked)
    return rows


def truncate(text, width):
    result, used = '', 0
    for char in safe(text):
        used += 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if used >= width:
            break
        result += char
    return result


class Screen:
    def __init__(self, stream, log, host):
        self.stream, self.log, self.host = stream, log, host
        self.rows, self.history = {}, []
        self.footer = 0
        self.tty = stream.isatty()
        self.width = None

    def update(self, name, status, detail, checked=None):
        checked = checked or timestamp()
        detail = safe(detail)
        old = self.rows.get(name)
        self.rows[name] = (status, detail, checked)
        if old is None or old[0] != status or (name == 'COMMAND' and old[1] != detail):
            record = {'time': timestamp(), 'item': name, 'before': old[0] if old else None,
                      'status': status, 'detail': detail, 'checked_at': checked}
            self.log.write(json.dumps(record, ensure_ascii=False) + '\n')
            self.log.flush()
            self.history.append(f'[{datetime.fromisoformat(record["time"]).strftime("%Y-%m-%d %H:%M:%S")}]\n'
                                f'{name}: {old[0] if old else "미확인"} → {status}\n{detail}\n\n')

    def draw(self):
        size = shutil.get_terminal_size((110, 30))
        if self.tty and self.footer:
            self.stream.write(f'\033[{self.footer}A\r\033[J')
        if self.tty and size.columns != self.width and self.footer:
            self.stream.write('\n')
        had_history = bool(self.history)
        for entry in self.history:
            self.stream.write(entry)
        self.history.clear()
        lines = [('─' * 70, None), (f'현재 상태 · 로버: {self.host}', None),
                 (f'마지막 화면 갱신: {datetime.now():%Y-%m-%d %H:%M:%S}', None),
                 ('항목            상태          상세', None)]
        for name in ORDER:
            status, detail, checked = self.rows.get(name, ('검사 중', '검사 대기', None))
            color = '32' if status in ('정상', '연결됨', '처리 완료') else '31' if status in ('실패', '끊김') else '33' if status in ('지연', '검사 중', '처리 중', '수신 대기') else '90'
            padding = max(1, 12 - sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in status))
            lines.append((f'{name:<15} {status}{" " * padding}{local_time(checked)} · {detail}', color))
        lines += [('─' * 70, None), ('Ctrl+C: 진단만 종료 · 전체 이력: .runtime/diagnostics/', None)]
        if self.tty or not self.footer or had_history:
            if self.tty and size.lines < len(lines) + 2:
                # Keep a compact footer in a small window; details remain in the log.
                lines = lines[:3] + [(f'{n}: {self.rows.get(n, ("검사 중",))[0]}', None) for n in ORDER]
                lines = lines[:max(1, size.lines - 2)]
            for line, color in lines:
                line = truncate(line, size.columns)
                self.stream.write((f'\033[{color}m{line}\033[0m' if self.tty and color else line) + '\n')
            self.stream.flush()
        self.footer, self.width = len(lines), size.columns


def run(args):
    with open(args.config, 'rb') as f:
        cfg = tomllib.load(f)['diagnostics']
    for key in ('refresh', 'probe_interval', 'stale_after'):
        if type(cfg[key]) not in (int, float) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(f'diagnostics.{key} must be positive and finite')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    target_file = runtime / 'last_ssh_target'
    target = args.target or (target_file.read_text().strip() if target_file.exists() else None)
    host = args.host or (target.split('@')[-1] if target else '192.168.1.50')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', host):
        raise ValueError('로버 주소 형식이 올바르지 않습니다.')
    if target and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*', target):
        raise ValueError('SSH 주소는 user@host 형식이어야 합니다.')
    if target and target.split('@')[-1] != host:
        target = None  # Never inspect another rover with stale saved SSH information.
    control = runtime / ('ssh-control-' + target.replace('@', '_')) if target else None
    with open(runtime / 'diagnostics.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('진단 터미널이 이미 실행 중입니다.')
            return
        logs = runtime / 'diagnostics'
        logs.mkdir(exist_ok=True)
        path = logs / (datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')
        with open(path, 'a', encoding='utf-8') as log, concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            screen = Screen(sys.stdout, log, host)
            pending_probe, pending_backend = None, None
            next_probe = 0
            while True:
                if pending_probe is None and time.monotonic() >= next_probe:
                    pending_probe = pool.submit(probe, host, target, control)
                if pending_probe is not None and pending_probe.done():
                    for name, (status, detail, checked) in pending_probe.result().items():
                        screen.update(name, status, detail, checked)
                    pending_probe = None
                    next_probe = time.monotonic() + cfg['probe_interval']
                if pending_backend is None:
                    pending_backend = pool.submit(backend_rows, host)
                if pending_backend.done():
                    try:
                        rows = pending_backend.result()
                        age, connected, rx = rows.pop('DATA RECEIVED')
                        status = '수신 대기' if age is None else '정상' if connected and age < cfg['stale_after'] else '지연'
                        checked = (datetime.now().astimezone() - timedelta(seconds=age)).isoformat(timespec='seconds') if age is not None else timestamp()
                        screen.update('DATA RECEIVED', status, f'마지막 수신 {age}초 전 · RX {rx}' if age is not None else '아직 수신 없음', checked)
                        for name, (status, detail, checked) in rows.items():
                            screen.update(name, status, detail, checked)
                    except (OSError, ValueError, KeyError) as e:
                        for name in ('GROUNDLINK', 'DATA RECEIVED', 'COMMAND'):
                            screen.update(name, '확인 불가', 'GCS 백엔드: ' + safe(e))
                    pending_backend = None
                screen.draw()
                time.sleep(cfg['refresh'])


def main():
    parser = argparse.ArgumentParser(description='별도 터미널 로버 연결 진단')
    parser.add_argument('--host', help='진단할 로버 IP')
    parser.add_argument('--target', help='SSH user@host; 기본: 로버 시작에서 저장한 주소')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    try:
        run(parser.parse_args())
    except KeyboardInterrupt:
        print('\n진단 종료 · 지상국 통신은 유지됩니다.')
    except (OSError, ValueError, KeyError) as e:
        parser.exit(1, f'진단 시작 실패: {e}\n')


if __name__ == '__main__':
    main()
