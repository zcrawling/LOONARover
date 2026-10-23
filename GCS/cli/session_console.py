"""Read operator commands in the GCS launch terminal."""
import argparse
import os
import math
import select
import sys
import time

from cli.common import request, safe


def handle(line):
    action = line.strip().lower()
    if action.split()[:1] == ['exposure']:
        try:
            words = action.split()[1:]
            if not words:
                query = {'operation': 'status'}
            elif len(words) != 1:
                raise ValueError('사용법: exposure [+|-|EV값|backlight|auto]')
            elif words[0] in ('auto', 'backlight'):
                query = {'operation': words[0]}
            elif words[0] in ('+', '-'):
                query = {'operation': 'add', 'value': .5 if words[0] == '+' else -.5}
            else:
                ev = float(words[0])
                if not math.isfinite(ev) or not -3 <= ev <= 3:
                    raise ValueError('EV 범위: -3~+3')
                query = {'operation': 'set', 'value': ev}
            result = request(dict(action='camera', **query), timeout=10)
            print('[LOONAR] ' + safe(result.get('text', '카메라 응답 없음')), flush=True)
        except (OSError, ValueError) as error:
            print(f'[LOONAR] 노출 조절 실패: {safe(error)}', flush=True)
        return
    if action not in ('flip', 'obj'):
        if line.strip():
            print('[LOONAR] 명령: flip (반전 전환), obj (객체인식 ON/OFF), exposure [+|-|EV|backlight|auto], Ctrl+C (종료)', flush=True)
        return
    try:
        result = request({'action': action}, timeout=2)
        print('[LOONAR] ' + result.get('text', '전환 실패'), flush=True)
    except (OSError, ValueError) as error:
        print(f'[LOONAR] {action} 전환 실패: {error}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-pid', type=int)
    args = parser.parse_args()
    print('[LOONAR] flip + Enter: 반전 전환 / obj + Enter: 객체인식 ON/OFF (기본 ON) / Ctrl+C: 종료', flush=True)
    print('[LOONAR] 노출: exposure + / exposure - (0.5EV씩), exposure 1.5, exposure backlight, exposure auto', flush=True)
    stdin_open = True
    while True:
        if args.server_pid:
            try:
                os.kill(args.server_pid, 0)
            except ProcessLookupError:
                return
        if stdin_open:
            if not select.select([sys.stdin], [], [], .2)[0]:
                continue
            line = sys.stdin.readline()
            if line:
                handle(line)
            else:
                stdin_open = False
        elif args.server_pid:
            time.sleep(.2)
        else:
            return


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
