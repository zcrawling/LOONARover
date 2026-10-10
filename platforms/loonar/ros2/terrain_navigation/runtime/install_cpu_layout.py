#!/usr/bin/env python3
"""Install/restore the Pi CPU layout. Run with sudo; no firmware or motion IO."""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess

HERE = Path(__file__).resolve().parent
STATE = Path('/var/lib/loonar-cpu-layout')
MANIFEST = STATE/'original.json'
BOOT = Path('/boot/firmware/cmdline.txt')
BOOT_ARGS = ['nohz_full=1-3', 'rcu_nocbs=1-3', 'irqaffinity=0', 'isolcpus=managed_irq,1-3']


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--user', default='loonar')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('run this installer with sudo')
    if args.remove:
        restore()
        return
    user = pwd.getpwnam(args.user)
    if user.pw_uid == 0 or not args.user.replace('_','').replace('-','').isalnum():
        parser.error('a normal local user is required')
    if Path('/sys/devices/system/cpu/online').read_text().strip() != '0-3':
        parser.error('this profile requires exactly CPU 0-3')
    if 'cpuset' not in Path('/sys/fs/cgroup/cgroup.controllers').read_text().split():
        parser.error('cgroup v2 cpuset is required')
    # Do not move an active rover while changing the launch/recording code.
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            cmd = (proc/'cmdline').read_bytes().replace(b'\0', b' ')
            if b'-m mcu_v2.backend ' in cmd or b'vehicle_gatewayd --runtime-dir' in cmd:
                parser.error('stop the running rover before installing CPU placement')
        except (FileNotFoundError, ProcessLookupError):
            pass
    cmdline = BOOT.read_text().strip()
    for argument in BOOT_ARGS:
        key = argument.split('=')[0]+'='
        if any(a.startswith(key) and a != argument for a in cmdline.split()):
            parser.error(f'existing boot parameter conflicts with {argument}')
    config = Path('/boot/config-'+os.uname().release).read_text()
    for flag in ('CONFIG_NO_HZ_FULL=y', 'CONFIG_RCU_NOCB_CPU=y', 'CONFIG_CPUSETS=y'):
        if flag not in config:
            parser.error(f'kernel missing {flag}')
    files = {
        '/etc/loonar/cpu-layout.json': json.dumps({'uid':user.pw_uid,'user':args.user,'os':[0,1,2,3],'work':[1,2,3],'control':[0]}, indent=2)+'\n',
        '/usr/local/sbin/loonar-cpu-enter': (HERE/'cpu_enter.py').read_text(),
        '/usr/local/lib/loonar/kernel_housekeeping.py': (HERE/'kernel_housekeeping.py').read_text(),
        '/etc/sudoers.d/loonar-cpu-layout': f'{args.user} ALL=(root) NOPASSWD: /usr/local/sbin/loonar-cpu-enter work *, /usr/local/sbin/loonar-cpu-enter control *\n',
        '/etc/systemd/system.conf.d/90-loonar-cpu.conf': '[Manager]\nCPUAffinity=0 1 2 3\n',
        '/etc/systemd/system/loonar.slice': '[Unit]\nDescription=LOONAR CPU pools\n[Slice]\nAllowedCPUs=0-3\n',
        '/etc/systemd/system/loonar-work.slice': '[Unit]\nDescription=LOONAR sensors ROS and recording\n[Slice]\nAllowedCPUs=1 2 3\n',
        '/etc/systemd/system/loonar-control.slice': '[Unit]\nDescription=LOONAR MCU and vehicle gateway\n[Slice]\nAllowedCPUs=0\n',
        '/etc/systemd/system/loonar-cpu-housekeeping.service': '[Unit]\nDescription=LOONAR movable kernel work and IRQ placement\nAfter=systemd-udev-trigger.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I /usr/local/lib/loonar/kernel_housekeeping.py\n[Install]\nWantedBy=multi-user.target\n',
        '/etc/systemd/system/loonar-cpu-housekeeping.timer': '[Unit]\nDescription=Maintain IRQ placement after device discovery\n[Timer]\nOnBootSec=30s\nOnUnitActiveSec=30s\nUnit=loonar-cpu-housekeeping.service\n[Install]\nWantedBy=timers.target\n',
    }
    for unit, section in [('system.slice','Slice'),('user.slice','Slice'),('init.scope','Scope')]:
        files[f'/etc/systemd/system/{unit}.d/90-loonar-cpu.conf'] = f'[{section}]\nAllowedCPUs=0-3\n'
    files[str(BOOT)] = ' '.join(cmdline.split()+[a for a in BOOT_ARGS if a not in cmdline.split()])+'\n'
    STATE.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.exists():
        original = {'files': {}, 'cpusets': {}, 'kernel_masks': {}, 'pid1_affinity': sorted(os.sched_getaffinity(1))}
        for name in files:
            p = Path(name)
            original['files'][name] = {'text':p.read_text(),'mode':p.stat().st_mode & 0o777} if p.exists() else None
        for unit in ('system.slice','user.slice','init.scope'):
            original['cpusets'][unit] = (Path('/sys/fs/cgroup')/unit/'cpuset.cpus').read_text().strip() if (Path('/sys/fs/cgroup')/unit/'cpuset.cpus').exists() else ''
        masks = [Path('/proc/irq/default_smp_affinity'),Path('/sys/devices/virtual/workqueue/cpumask')]
        masks += list(Path('/sys/bus/workqueue/devices').glob('*/cpumask')) + list(Path('/proc/irq').glob('[0-9]*/smp_affinity_list'))
        for p in masks:
            original['kernel_masks'][str(p)] = p.read_text()
        MANIFEST.write_text(json.dumps(original, indent=2)+'\n')
    for name, text in files.items():
        p = Path(name); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        p.chmod(0o440 if 'sudoers.d' in name else 0o755 if name.endswith('loonar-cpu-enter') else 0o644)
    run('visudo','-cf','/etc/sudoers.d/loonar-cpu-layout')
    run('systemctl','daemon-reload')
    run('systemctl','start','loonar-work.slice','loonar-control.slice')
    for unit in ('system.slice','user.slice','init.scope'):
        run('systemctl','set-property','--runtime',unit,'AllowedCPUs=0-3')
    # Manager default applies to new services immediately after daemon-reload.
    # Also clear the old inherited CPU0 affinity on existing ordinary OS tasks.
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            group = (proc/'cgroup').read_text().strip().split('::', 1)[-1]
            if not group.startswith(('/system.slice/', '/user.slice/')):
                continue
            for task in (proc/'task').iterdir():
                try:
                    if os.sched_getaffinity(int(task.name)) == {0}:
                        os.sched_setaffinity(int(task.name), {0,1,2,3})
                except ProcessLookupError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
    # Runtime PID1 placement now; defaults also persist across reboot.
    os.sched_setaffinity(1,{0,1,2,3})
    if subprocess.run(['systemctl','is-active','--quiet','irqbalance']).returncode == 0:
        # The profile's timer owns IRQ routing. Preserve original state for undo.
        state = json.loads(MANIFEST.read_text()); state['irqbalance_was_active'] = True
        MANIFEST.write_text(json.dumps(state,indent=2)+'\n')
        run('systemctl','stop','irqbalance')
    run('systemctl','enable','--now','loonar-cpu-housekeeping.service','loonar-cpu-housekeeping.timer')
    print('APPLIED: OS=0-3, control=0, work=1-3 (CPU0 excluded). Current kernel IRQ/workqueue placement applied.')
    boot_active = set(Path('/proc/cmdline').read_text().split())
    print(('BOOT OPTIONS ACTIVE: ' if set(BOOT_ARGS) <= boot_active else 'STAGED FOR NEXT BOOT: ')+' '.join(BOOT_ARGS))
    print('No kernel rebuild. No reboot or rover startup performed.')


def restore():
    original = json.loads(MANIFEST.read_text())
    # Caller must stop rover scopes first; never kill running control implicitly.
    active = run('systemctl','list-units','--no-legend','--plain','loonar-*.scope')
    if active.strip():
        raise SystemExit('stop LOONAR scopes before removing CPU placement')
    subprocess.run(['systemctl','disable','--now','loonar-cpu-housekeeping.timer','loonar-cpu-housekeeping.service'],check=False)
    for name, saved in original['files'].items():
        p=Path(name)
        if saved is None: p.unlink(missing_ok=True)
        else:
            p.write_text(saved['text']); p.chmod(saved['mode'])
    run('systemctl','daemon-reload')
    for unit, value in original['cpusets'].items():
        run('systemctl','set-property','--runtime',unit,'AllowedCPUs='+value)
    os.sched_setaffinity(1,set(original['pid1_affinity']))
    for name,value in original['kernel_masks'].items():
        try: Path(name).write_text(value)
        except OSError: pass
    if original.get('irqbalance_was_active'): run('systemctl','start','irqbalance')
    print('Original files and runtime CPU masks restored. Boot-parameter changes take effect after reboot.')


if __name__ == '__main__':
    main()
