"""Read-only helper sent over SSH stdin by payload_csv.py; never installed on Pi."""
import json
from pathlib import Path


def read_capture(query, roots):
    matches = []
    seq = int(query['sample'])
    for root in roots:
        for sidecar in root.glob(f'payload-*-seq{seq:06d}-*.events.jsonl'):
            try:
                if sidecar.stat().st_size > 65536:
                    continue
                for line in sidecar.read_text().splitlines():
                    event = json.loads(line)
                    if event.get('event') not in ('END', 'RESULT_RECOVERED'):
                        continue
                    if event.get('payload_seq_id') != seq:
                        continue
                    # RESULT recovery can use a new command request ID. The MCU's
                    # persistent boot counter plus UID/sequence still identifies
                    # the original capture exactly.
                    identity = query.get('mcu_uid') and query.get('mcu_boot') is not None
                    if not identity and str(event.get('request_id')) != str(query['request_id']):
                        continue
                    if query.get('mcu_uid') and event.get('mcu_uid') != query['mcu_uid']:
                        continue
                    if query.get('mcu_boot') is not None and event.get('mcu_boot_id') != query['mcu_boot']:
                        continue
                    csv = sidecar.with_suffix('').with_suffix('.csv')
                    if csv.resolve().parent != root.resolve():
                        continue
                    matches.append((event.get('stamp_ns', 0), csv))
            except (OSError, ValueError, TypeError):
                continue
    for _, csv in sorted(matches, key=lambda item:item[0], reverse=True):
        size = csv.stat().st_size
        if size > 2_000_000:
            return {'error': 'CSV가 2 MB를 초과합니다'}
        content = csv.read_text(encoding='ascii')
        # A recovered PCA-only file must not hide the original raw capture.
        if not any(line.split(',')[0].isdigit() and len(line.split(',')) == 14 for line in content.splitlines()):
            continue
        return {'filename': csv.name, 'bytes': size, 'csv': content}
    return {'error': '해당 시퀀스의 완료된 원시 CSV를 찾지 못했습니다'}


def main(query):
    roots = [Path('/var/lib/loonar/payload'), Path.home() / 'loonar-motor-bench/runtime/payload']
    if query.get('directory'):
        roots.insert(0, Path(query['directory']).expanduser())
    try:
        print(json.dumps(read_capture(query, roots), ensure_ascii=True))
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'error': f'CSV 읽기 실패: {type(error).__name__}'}))


if __name__ == '__main__':
    main(query)  # Supplied as a Python literal over stdin, never shell interpolation.
