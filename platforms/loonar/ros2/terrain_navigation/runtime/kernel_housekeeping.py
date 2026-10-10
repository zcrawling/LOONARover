#!/usr/bin/python3 -I
"""Best-effort movable kernel work on CPU0; never moves bound per-CPU threads."""
import json
import os
from pathlib import Path


def apply():
    result = {'applied': [], 'unsupported': [], 'kernel_threads': []}
    paths = [Path('/proc/irq/default_smp_affinity'),
             Path('/sys/devices/virtual/workqueue/cpumask')]
    paths += list(Path('/sys/bus/workqueue/devices').glob('*/cpumask'))
    paths += list(Path('/proc/irq').glob('[0-9]*/smp_affinity_list'))
    for path in paths:
        value = '0' if path.name == 'smp_affinity_list' else '1'
        try:
            path.write_text(value + '\n')
            result['applied'].append(str(path))
        except OSError as error:
            result['unsupported'].append({'path': str(path), 'error': str(error)})
    # RCU offload and unbound kthreads can migrate; bound workers/timers cannot.
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            name = (proc/'comm').read_text().strip()
            if (proc/'cmdline').read_bytes() or not (
                name.startswith(('rcuo', 'rcug', 'kworker/u')) or name in ('kthreadd', 'kswapd0', 'kcompactd0')):
                continue
            os.sched_setaffinity(int(proc.name), {0})
            result['kernel_threads'].append({'pid': int(proc.name), 'name': name})
        except (OSError, ValueError):
            pass
    Path('/run/loonar-cpu-housekeeping.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    apply()
