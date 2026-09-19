import argparse
import json
import sys
import time
from backend.config import DEFAULT_CONFIG, load
from .common import request, safe


def render(s):
    status = s["status"] or {}
    lines = ["LOONAR 상태 창 | MOCK / 예시 데이터", f"TCP: {s['connection']} | 모드: {status.get('mode', '—')}",
             f"상태 경과: {s['status_age']}초 | {'오래된 데이터' if s['status_stale'] else '갱신 중'}",
             f"수신 {s['rx_messages']} / 송신 {s['tx_messages']} | 데이터 누락 구간 {s['data_gaps']}회",
             f"오류: {s['error'] or '—'}", "", "주요 상태"]
    for key, value in status.get("values", {}).items():
        lines.append(f"  {key}: {'—' if value is None else value}")
    p = status.get("payload", {})
    lines += ["", f"PAYLOAD: {p.get('state', '—')} | 요청 {p.get('request_id', '—')}"]
    sample = s["payload_sample"]
    if sample:
        lines += [f"샘플 {sample['sample']} | {sample.get('time', '—')} | {'이전 측정값' if s['sample_stale'] else '실시간'}"]
        for key, value in sample["values"].items():
            lines.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
    lines += ["", "단절 중 누락된 측정값은 복구하지 않습니다.", "최근 이벤트"]
    lines += [f"  {e['time']} {e['text']}" for e in s["events"][-5:]]
    return "\n".join(safe(line) for line in lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--once", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config = load(args.config)
    try:
        while True:
            try:
                s = request({"action": "state"})
                output = json.dumps(s, ensure_ascii=False, indent=2) if args.json else render(s)
            except (OSError, ValueError) as exc:
                output = f"백엔드 연결 실패: {safe(exc)}"
            if sys.stdout.isatty() and not args.once:
                print("\033[2J\033[H", end="")
            print(output, flush=True)
            if args.once:
                return
            time.sleep(config["display"]["refresh"])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
