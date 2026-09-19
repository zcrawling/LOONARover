import argparse
import select
import sys
import time

from .common import request, safe

HELP = "STOP | MANUAL | AUTO | PAYLOAD | REACTION | status | help | quit\n방향 command·영상 원격 제어: TBD / 조이스틱: 후속 개발"


def execute(line):
    line = line.strip()
    if not line:
        return
    if line.lower() == "help":
        print(HELP)
    elif line.lower() == "status":
        s = request({"action": "state"})
        print(safe(f"{s['source']} | TCP {s['connection']} | {(s['status'] or {}).get('mode', '—')}"))
    else:
        result = request({"action": "command", "command": line.upper()})
        print(safe(f"{result['text']}  {result.get('request_id', '')}"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--command", help="Send one command and exit; use interactive mode for later responses")
    args = p.parse_args()
    if args.command:
        try:
            execute(args.command)
        except (OSError, ValueError) as exc:
            p.exit(1, f"백엔드 연결 실패: {exc}\n")
        return
    print("LOONAR 명령 창 — MOCK / 예시 데이터\n" + HELP)
    last_event = 0
    error_shown = False
    print("> ", end="", flush=True)
    try:
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], 0.3)
            if readable:
                line = sys.stdin.readline()
                if not line or line.strip().lower() in {"quit", "exit"}:
                    return
                try:
                    execute(line)
                except (OSError, ValueError) as exc:
                    print(f"백엔드 연결 실패: {safe(exc)}")
                print("> ", end="", flush=True)
            try:
                s = request({"action": "state"})
                events = s["events"]
                if events and events[-1]["id"] < last_event:
                    last_event = 0
                fresh = [e for e in events if e["id"] > last_event]
                for e in fresh:
                    print(f"\n{safe(e['time'])} {safe(e['text'])} [{safe(e['request_id'] or '-')}]")
                    last_event = e["id"]
                if fresh:
                    print("> ", end="", flush=True)
                error_shown = False
            except (OSError, ValueError):
                if not error_shown:
                    print("\n백엔드에 연결할 수 없습니다. backend.app 실행을 확인하세요.")
                    error_shown = True
                time.sleep(0.5)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
