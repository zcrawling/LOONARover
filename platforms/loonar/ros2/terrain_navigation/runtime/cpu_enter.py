#!/usr/bin/python3 -I
"""Root-installed narrow helper: move a caller-owned process to a CPU scope.

Never executes caller commands as root. Invoked by sudo with profile and PID.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise SystemExit('usage: sudo loonar-cpu-enter work|control PID')
    profile, pid_text = sys.argv[1:]
    if profile not in ('work', 'control') or not pid_text.isdecimal():
        raise SystemExit('invalid CPU profile or PID')
    config = json.loads(Path('/etc/loonar/cpu-layout.json').read_text())
    caller = int(os.environ.get('SUDO_UID', '-1'))
    pid = int(pid_text)
    if caller != config['uid'] or pid <= 1 or Path(f'/proc/{pid}').stat().st_uid != caller:
        raise SystemExit('only the configured user can move its own processes')
    cpus = set(config[profile])
    cgroup = Path(f'/proc/{pid}/cgroup').read_text()
    target = f'/loonar.slice/loonar-{profile}.slice/'
    if target not in cgroup:
        start = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        unit = f'loonar-{profile}-{pid}-{start}.scope'
        subprocess.run([
            '/usr/bin/busctl', 'call', 'org.freedesktop.systemd1',
            '/org/freedesktop/systemd1', 'org.freedesktop.systemd1.Manager',
            'StartTransientUnit', 'ssa(sv)a(sa(sv))', unit, 'fail', '3',
            'Slice', 's', f'loonar-{profile}.slice',
            'PIDs', 'au', '1', str(pid),
            'CollectMode', 's', 'inactive-or-failed', '0',
        ], check=True, stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 2
        while target not in Path(f'/proc/{pid}/cgroup').read_text():
            if time.monotonic() > deadline:
                raise SystemExit('systemd CPU scope did not become ready')
            time.sleep(.01)
    # Scope cpuset is authoritative; clear inherited CPU0 affinity as well.
    for task in Path(f'/proc/{pid}/task').iterdir():
        try:
            os.sched_setaffinity(int(task.name), cpus)
        except ProcessLookupError:
            pass
    effective = os.sched_getaffinity(pid)
    if effective != cpus or target not in Path(f'/proc/{pid}/cgroup').read_text():
        raise SystemExit(f'CPU placement failed: {effective}')


if __name__ == '__main__':
    main()
