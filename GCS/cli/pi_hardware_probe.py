"""Standalone read-only collector, streamed to Pi's python3 over SSH stdin."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time


def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=.8)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_pmic(text):
    values = {}
    for name, value, unit in re.findall(r'(\w+)\s+(?:volt|current)\(\d+\)=([\d.eE+-]+)([VA])', text or ''):
        number = float(value)
        if math.isfinite(number):
            values[name] = {'value': number, 'unit': unit}
    return values


def wireless(text):
    rows = []
    for line in text.splitlines():
        if ':' not in line:
            continue
        name, rest = line.split(':', 1)
        fields = rest.split()
        try:
            quality, signal = float(fields[1]), float(fields[2])
            if signal > 0:
                signal -= 256  # Wireless extensions unsigned dBm representation.
            rows.append(dict(interface=name.strip(), quality=quality, signal_dbm=signal))
        except (IndexError, ValueError):
            continue
    return rows


def read_status(role, now, boot_id, directories=None):
    directories = directories or [Path(f'/tmp/loonar-monitor-{uid}') for uid in {os.getuid(), 0}]
    candidates = []
    for directory in directories:
        try:
            data = json.loads((directory / f'{role}.json').read_text())
            if data.get('boot_id') != boot_id or data.get('role') != role:
                continue
            age = now - data['updated_mono']
            if not math.isfinite(age) or age < 0:
                continue
            candidates.append((age, data))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not candidates:
        return {'online': False, 'available': False}
    age, data = min(candidates, key=lambda item: item[0])
    data['available'] = True
    data['snapshot_age_s'] = age
    data['stale'] = age > 3
    data['online'] = bool(data.get('online') and not data['stale'])
    for field in ('last_rx', 'last_tx', 'health', 'motor'):
        stamp = data.get(field + '_mono')
        data[field + '_age_s'] = max(0, now-stamp) if isinstance(stamp, (int, float)) else None
    if not data['online'] or data['health_age_s'] is None or data['health_age_s'] > 3:
        data['temperature_c'] = None
    motor = data.get('motor') or {}
    motor_fresh = data['online'] and data['motor_age_s'] is not None and data['motor_age_s'] < 1
    data['battery_v'] = motor.get('main_voltage_v') if motor_fresh and motor.get('main_voltage_valid') else None
    data['driver_temperature_c'] = motor.get('temperature_c') if motor_fresh and motor.get('temperature_valid') else None
    return data


def collect():
    temp = command('vcgencmd', 'measure_temp')
    match = re.search(r'temp=([\d.+-]+)', temp or '')
    pmic = parse_pmic(command('vcgencmd', 'pmic_read_adc', 'EXT5V_V'))
    throttled = command('vcgencmd', 'get_throttled')
    try:
        wifi = wireless(Path('/proc/net/wireless').read_text())
    except OSError:
        wifi = []
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    now = time.monotonic()
    control = read_status('control', now, boot)
    payload = read_status('payload', now, boot)
    for data, serial in ((control, '19971280'), (payload, '21147480')):
        data['usb_present'] = Path(f'/dev/serial/by-id/usb-Teensyduino_USB_Serial_{serial}-if00').exists()
    return dict(sample_ns=time.time_ns(), cpu_temperature_c=float(match[1]) if match else None,
                input_voltage_v=pmic.get('EXT5V_V', {}).get('value'),
                throttled=throttled, wireless=wifi,
                control=control, payload=payload)


if __name__ == '__main__':
    try:
        while True:
            start = time.monotonic()
            print(json.dumps(collect(), allow_nan=False), flush=True)
            time.sleep(max(.05, 1 - (time.monotonic() - start)))
    except (BrokenPipeError, KeyboardInterrupt):
        pass
