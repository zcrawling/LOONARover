"""UDP receive-only hardware dashboard; legacy formatting/probe helpers retained."""
import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import time

from backend.config import ROOT
from cli.common import safe
from cli.diagnostics import truncate


def number(value, unit=''):
    return f'{value:.2f}{unit}' if type(value) in (int, float) else 'N/A'


def last_io(status, direction, elapsed):
    stamp = status.get(f'last_{direction}_ns')
    age = status.get(f'last_{direction}_age_s')
    if stamp is None or age is None:
        return '—'
    when = datetime.fromtimestamp(stamp / 1e9).astimezone().strftime('%H:%M:%S')
    return f'{when} ({age + elapsed:.1f}초 전)'


def lines(host, packet, elapsed, error=''):
    stale = elapsed > 4 or bool(error)
    rows = [f'LOONAR | {host} | {datetime.now():%H:%M:%S}',
            f'{error or ("갱신 지연" if stale else "연결됨 · 1초 갱신")}', '']
    p = packet if packet and not stale else {}
    try:
        flags = int(p['throttled'].split('=')[1], 16)
        power = f'현재 {"발생" if flags & 1 else "없음"} / 과거 기록 {"있음" if flags & (1 << 16) else "없음"}'
    except (KeyError, TypeError, ValueError, IndexError):
        power = 'N/A'
    rows += [f'Pi CPU 온도       {number(p.get("cpu_temperature_c"), " °C")}',
             f'Pi 입력 전압      {number(p.get("input_voltage_v"), " V")}  (PMIC ADC)',
             f'Pi 저전압         {power}']
    wifi = p.get('wireless', [])
    rows.append('Wi-Fi 신호        ' + (' / '.join(f'{w["signal_dbm"]:.0f} dBm ({w["interface"]})' for w in wifi) or 'N/A'))
    control = p.get('control', {})
    rows += ['', f'배터리 전압       {number(control.get("battery_v"), " V")}  (RoboClaw)',
             f'드라이버 온도     {number(control.get("driver_temperature_c"), " °C")}',
             '모터 본체 온도    미지원', '']
    for role in ('control', 'payload'):
        status = (packet or {}).get(role, {})
        state = 'STALE' if stale or status.get('stale') else 'ONLINE' if status.get('online') else 'OFFLINE'
        if not stale and not status.get('online'):
            if status.get('usb_present') is False:
                state = 'USB 미연결'
            elif status.get('usb_present') and not status.get('available'):
                state = 'USB 연결 · 통신 상태 기록 없음'
        temp = status.get('temperature_c') if state == 'ONLINE' else None
        rows.append(f'{role.upper():7}  {state:7}  온도 {number(temp, " °C")}')
        rows.append(f'  TX {last_io(status, "tx", elapsed)} | RX {last_io(status, "rx", elapsed)}')
    rows += ['', 'TX: Pi→MCU / RX: MCU→Pi  ·  Ctrl+C: 모니터 종료']
    return rows


def draw(host, packet, received, error):
    elapsed = time.monotonic() - received if received is not None else 0
    rows = lines(host, packet, elapsed, error)
    if sys.stdout.isatty():
        width = shutil.get_terminal_size((100, 24)).columns
        print('\033[H' + '\n'.join('\033[2K' + truncate(row, width) for row in rows) + '\033[J', end='', flush=True)
    else:
        print('\n'.join(safe(row) for row in rows), flush=True)


def ssh_command(host, user):
    env = dict(os.environ)
    args = ['ssh', '-T', '-o', 'ConnectTimeout=4', '-o', 'ServerAliveInterval=2',
            '-o', 'ServerAliveCountMax=2', '-o', 'StrictHostKeyChecking=accept-new']
    if shutil.which('sshpass'):
        args = ['sshpass', '-e', *args, '-o', 'NumberOfPasswordPrompts=1']
        env['SSHPASS'] = os.environ.get('LOONAR_SSH_PASSWORD', 'loonar')
    else:
        args += ['-o', 'BatchMode=yes']
    return args + [f'{user}@{host}', 'python3 -u -'], env


def run(args):
    packet, received = None, None
    source = Path(__file__).with_name('pi_hardware_probe.py').read_bytes()
    while True:
        command, env = ssh_command(args.host, args.user)
        process = None
        error = '연결 중'
        try:
            process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process.stdin.write(source)
            process.stdin.close()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 'out')
                selector.register(process.stderr, selectors.EVENT_READ, 'err')
                buffer = b''
                while process.poll() is None or selector.get_map():
                    for key, _ in selector.select(1):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        if key.data == 'err':
                            error = safe(data.decode(errors='replace').strip())[-240:]
                            continue
                        buffer += data
                        if len(buffer) > 262144:
                            raise ValueError('모니터 응답 크기 초과')
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            packet = json.loads(line)
                            received = time.monotonic()
                            error = ''
                            if args.once:
                                draw(args.host, packet, received, error)
                                return
                    draw(args.host, packet, received, error)
            error = error or f'SSH 종료 ({process.returncode})'
        except (OSError, ValueError) as exc:
            error = safe(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
        draw(args.host, packet, received, error)
        if args.once:
            raise RuntimeError(error)
        time.sleep(2)


def main():
    from cli.status_udp import run as receive_status
    parser = argparse.ArgumentParser(description='UDP 수신 전용 온도·전압·MCU 모니터')
    parser.add_argument('--host', '--rover-ip', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    try:receive_status('hardware',args.host,once=args.once)
    except KeyboardInterrupt:pass


if __name__ == '__main__':
    main()
