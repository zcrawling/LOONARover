"""Read operator commands in the GCS launch terminal."""
import argparse
import os
import select
import sys
import time

from cli.common import request


def handle(line):
    if line.strip().lower() != 'flip':
        if line.strip():
            print('[LOONAR] 명령: flip (반전 전환), Ctrl+C (종료)', flush=True)
        return
    try:
        result = request({'action': 'flip'}, timeout=2)
        print('[LOONAR] ' + result.get('text', '반전 전환 실패'), flush=True)
    except (OSError, ValueError) as error:
        print(f'[LOONAR] 반전 전환 실패: {error}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-pid', type=int)
    args = parser.parse_args()
    print('[LOONAR] flip + Enter: 영상·수동주행 반전 전환 / Ctrl+C: 종료', flush=True)
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
