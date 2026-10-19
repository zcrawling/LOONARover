"""Fetch completed payload captures without blocking GroundLink or changing Pi files."""
import asyncio
import json
import math
import os
from pathlib import Path

from cli.hardware_monitor import ssh_command


def sample_key(sample):
    return json.dumps([sample.get(k) for k in ('request_id', 'sample', 'time', 'mcu_uid', 'mcu_boot')], separators=(',', ':'))


def parse_capture(content, sample):
    rows = []
    result = None
    for line in content.splitlines():
        fields = line.split(',')
        if len(fields) == 16 and fields[0] == 'PCA' and fields[2] == str(sample['sample']):
            result = fields
        if len(fields) != 14 or not fields[0].isdigit():
            continue
        try:
            stamp = int(fields[0])
            if not 0 <= stamp <= 0xffffffff:
                continue
            values = []
            for index, valid in ((6, 11), (9, 12), (4, 10)):
                value = float(fields[index])
                ok = fields[valid] == '1' and (index != 9 or int(fields[13], 16) == 0)
                values.append(value if ok and math.isfinite(value) else None)
            rows.append((stamp, values))
        except (ValueError, OverflowError):
            continue
    if result is None:
        raise ValueError('CSV에 시퀀스 완료 결과가 없습니다')
    if result[1] != sample['values']['PCA model']['value']:
        raise ValueError('CSV와 수신 결과의 모델이 다릅니다')
    start, end = int(result[3]), int(result[4])
    duration = (end - start) & 0xffffffff
    points = []
    for stamp, values in rows:
        elapsed = (stamp - start) & 0xffffffff
        if elapsed <= duration:
            points.append({'t': elapsed / 1000, 'values': values,
                           'gap_before': bool(points and elapsed/1000 - points[-1]['t'] > 1.5)})
    if not points:
        raise ValueError('CSV에 해당 시퀀스의 센서 표본이 없습니다')
    # Bound the local API response. Preserve every fault boundary along with
    # regularly spaced points so downsampling never draws over a missing sensor.
    stride = max(1, math.ceil(len(points) / 600))
    indices = set(range(0, len(points), stride)) | {0, len(points)-1}
    for i in range(1, len(points)):
        if points[i]['gap_before'] or [v is None for v in points[i]['values']] != [v is None for v in points[i-1]['values']]:
            indices.update((i-1, i))
    if len(indices) > 2000:
        raise ValueError('센서 오류 구간이 너무 많아 그래프를 표시할 수 없습니다')
    return dict(key=sample_key(sample), sample=sample['sample'], duration_s=duration/1000,
                sample_count=len(points), points=[points[i] for i in sorted(indices)])


async def fetch_capture(host, sample):
    query = {k: sample.get(k) for k in ('request_id', 'sample', 'mcu_uid', 'mcu_boot')}
    query['directory'] = os.environ.get('LOONAR_PAYLOAD_CSV_DIR')
    source = ('query = ' + repr(query) + '\n' + Path(__file__).with_name('payload_csv_remote.py').read_text()).encode()
    command, env = ssh_command(host, os.environ.get('LOONAR_SSH_USER', 'loonar'))
    process = await asyncio.create_subprocess_exec(*command, env=env, stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(15):
            process.stdin.write(source)
            await process.stdin.drain()
            process.stdin.close()
            chunks, size = [], 0
            while chunk := await process.stdout.read(65536):
                size += len(chunk)
                if size > 4_100_000:
                    raise ValueError('CSV 응답 크기 초과')
                chunks.append(chunk)
            await process.wait()
        if process.returncode:
            raise ValueError('Pi SSH 연결 또는 CSV 읽기 실패')
        response = json.loads(b''.join(chunks))
        if response.get('error'):
            raise ValueError(response['error'])
        trace = parse_capture(response['csv'], sample)
        return dict(trace, filename=response['filename'], bytes=response['bytes'])
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def watch(state, fetch=fetch_capture):
    completed = None
    while True:
        sample = state.payload_sample
        if not sample or sample_key(sample) == completed:
            await asyncio.sleep(1)
            continue
        key = sample_key(sample)
        state.payload_trace_status = {'key': key, 'state': 'loading'}
        try:
            trace = await fetch(state.host, sample)
            if state.payload_sample and sample_key(state.payload_sample) == key:
                state.payload_trace = trace
                state.payload_trace_status = {'key': key, 'state': 'ready'}
                completed = key
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as error:
            if state.payload_sample and sample_key(state.payload_sample) == key:
                state.payload_trace_status = {'key': key, 'state': 'error', 'message': str(error)}
            await asyncio.sleep(10)
