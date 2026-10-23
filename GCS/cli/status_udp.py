"""Receive-only status terminal; also runs as a standalone Python file on PC .4.

No SSH, ping, GroundLink or command API is used. No acknowledgements are sent.
"""
import argparse
from datetime import datetime
import json
import math
import os
import socket
import sys
import time

PORTS = {'hardware':6101, 'communication':6102}


def decode(raw, peer, expected):
    if peer[0] != expected or len(raw) > 32768:
        raise ValueError('unexpected status sender')
    packet = json.loads(raw)
    if (packet.get('schema') != 1 or packet.get('kind') not in PORTS or
            packet.get('source') != expected or type(packet.get('seq')) is not int or
            packet['seq'] < 1 or type(packet.get('stamp_ns')) is not int or
            not isinstance(packet.get('data'),dict)):
        raise ValueError('invalid status packet')
    return packet


def number(value, unit=''):
    return f'{value:.2f}{unit}' if type(value) in (int,float) and math.isfinite(value) else 'N/A'


def io_line(status, direction, elapsed):
    stamp, age = status.get(f'last_{direction}_ns'), status.get(f'last_{direction}_age_s')
    if not isinstance(stamp,int) or type(age) not in (int,float): return '—'
    return datetime.fromtimestamp(stamp/1e9).strftime('%H:%M:%S') + f' ({age+elapsed:.1f}초 전)'


def render(kind, packet, age, gaps, host=None):
    stale = packet is None or age > 4
    data = {} if stale else packet['data']
    title = '온도·전압·MCU 상태' if kind=='hardware' else '통신 상태'
    rows = [f'LOONAR {title} | Pi {host or (packet or {}).get("source", "—")} | {datetime.now():%H:%M:%S}',
            f'UDP 수신 전용 · {"수신 대기/갱신 지연" if stale else "수신 정상"} · 누락 {gaps}', '']
    if kind == 'hardware':
        rows += [f"Pi CPU 온도       {number(data.get('cpu_temperature_c'),' °C')}",
                 f"Pi 입력 전압      {number(data.get('input_voltage_v'),' V')}",
                 f"저전압/스로틀링   {data.get('throttled','N/A')}"]
        wifi = data.get('wireless',[])
        rows.append('Wi-Fi 신호        '+(' / '.join(f"{w['signal_dbm']:.0f} dBm ({w['interface']})" for w in wifi) or 'N/A'))
        c = data.get('control',{})
        rows += [f"배터리 전압       {number(c.get('battery_v'),' V')}",
                 f"드라이버 온도     {number(c.get('driver_temperature_c'),' °C')}"]
        for role in ('control','payload'):
            status = data.get(role,{})
            state = 'ONLINE' if status.get('online') else 'OFFLINE' if not stale else '확인 불가'
            rows += ['', f"{role.upper():7} {state} · MCU 온도 {number(status.get('temperature_c'),' °C')}",
                     f"  TX {io_line(status,'tx',age)} | RX {io_line(status,'rx',age)}"]
    else:
        ground = data.get('groundlink',{})
        connected = ground.get('gcs_connected')
        rows += [
                 f"GCS TCP 연결      {'연결됨' if connected is True else '끊김' if connected is False else '확인 불가'}",
                 f"운용 모드         {ground.get('mode') or '확인 불가'}"]
        for name, value in data.get('components',{}).items():
            rows.append(f'{name:17} {"실행 중" if value else "실행 안 됨"}')
        for role in ('control','payload'):
            status = data.get(role,{})
            rows.append(f"{role.upper():7} MCU 통신 {'ONLINE' if status.get('online') else 'OFFLINE' if not stale else '확인 불가'}")
        rows += ['', 'SSH 로그인·ping·왕복 지연은 검사하지 않습니다.']
    rows += ['', 'Ctrl+C: 이 상태 창만 종료 · 조종 명령 전송 없음']
    return rows


def run(kind, host, bind='0.0.0.0', once=False):
    host = socket.gethostbyname(host)
    if kind == 'hardware':
        # Import lazily: this file remains a standalone UDP viewer on the second PC.
        try:
            from backend.hardware_status import HardwareStatus
        except ModuleNotFoundError:
            pass
        else:
            receiver = HardwareStatus(host, bind)
            try:
                while True:
                    packet, age, gaps = receiver.poll()
                    rows = render(kind, packet, age, gaps, host)
                    if sys.stdout.isatty() and os.name != 'nt': print('\033[2J\033[H', end='')
                    print('\n'.join(''.join(c if c.isprintable() else ' ' for c in row) for row in rows), flush=True)
                    if once and packet is not None and age <= 4: return packet
                    time.sleep(1)
            finally:
                receiver.close()
            return
    packet = None; received = 0; sequence = 0; boot = None; gaps = 0
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        # Deliberately no SO_REUSEPORT: a duplicate viewer must not steal packets.
        sock.bind((bind,PORTS[kind])); sock.settimeout(1)
        while True:
            try:
                raw, peer = sock.recvfrom(32769)
                value = decode(raw,peer,host)
                if value['kind'] != kind: continue
                session=(value.get('pi_boot_id'),value.get('publisher_session'))
                if session != boot:
                    boot=session;sequence=0
                if value['seq'] <= sequence: continue
                if sequence:gaps += max(0,value['seq']-sequence-1)
                packet=value; sequence=value['seq']; received=time.monotonic()
            except socket.timeout:
                pass
            except (ValueError,TypeError,KeyError):
                continue
            rows = render(kind,packet,time.monotonic()-received,gaps,host)
            if sys.stdout.isatty() and os.name != 'nt': print('\033[2J\033[H',end='')
            print('\n'.join(''.join(c if c.isprintable() else ' ' for c in row) for row in rows),flush=True)
            if once and packet is not None:return packet


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('kind',choices=PORTS)
    parser.add_argument('--host', '--rover-ip', required=True)
    parser.add_argument('--bind',default='0.0.0.0')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    try:run(args.kind,args.host,args.bind,args.once)
    except KeyboardInterrupt:pass

if __name__=='__main__':main()
