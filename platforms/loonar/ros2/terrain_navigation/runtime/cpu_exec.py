#!/usr/bin/env python3
"""Enter an installed CPU scope, then exec unchanged as the calling user."""
import os
from pathlib import Path
import subprocess
import sys


def enter(profile):
    if not Path('/etc/loonar/cpu-layout.json').exists():
        return
    subprocess.run(['sudo', '-n', '/usr/local/sbin/loonar-cpu-enter',
                    profile, str(os.getpid())], check=True)


if __name__ == '__main__':
    profile, separator, *command = sys.argv[1:]
    if profile not in ('work', 'control') or separator != '--' or not command:
        raise SystemExit('usage: cpu_exec.py work|control -- COMMAND ...')
    enter(profile)
    os.execvp(command[0], command)
