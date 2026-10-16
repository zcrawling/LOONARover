"""Pi recorder supervisor, sent over SSH in memory. Never publishes motion."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


def emit(kind, **fields):
    print(json.dumps(dict(event=kind, pi_epoch_ns=time.time_ns(), **fields)), flush=True)


def stop_process(child, timeout=90):
    if child.poll() is not None:
        return child.returncode
    # Let motor_bench stop hardware producers before flushing its recorder.
    child.send_signal(signal.SIGINT)
    try:
        return child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        raise RuntimeError('Recorder required forced termination; bag finalization unconfirmed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--existing-stack', action='store_true')
    p.add_argument('--video-ip')
    p.add_argument('--startup-timeout', type=float, default=90)
    a = p.parse_args()
    tools = a.root / 'platforms/loonar/tools'
    if not (tools / 'record-drive.sh').is_file():
        raise RuntimeError(f'Pi repository not found: {a.root}')
    a.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='preparing', start_pi_epoch_ns=time.time_ns(),
                 recording='ros2 bag record --all / MCAP', existing_stack=a.existing_stack)
    children, logs = [], []
    stopped = False

    def interrupted(*_):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)

    def start(name, command):
        log = (a.output / f'{name}.log').open('w')
        logs.append(log)
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True,
                                 env=dict(os.environ, PYTHONPATH=str(tools)+os.pathsep+os.environ.get('PYTHONPATH', '')))
        children.append(child)
        return child

    def snapshot():
        path = (a.output / 'recording-status.json' if a.existing_stack else
                a.output / 'runtime/recording-status.json')
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return dict(streams_fresh=False, missing_or_stale=['monitor_not_ready'])
        data['monitor_fresh'] = 0 <= time.time_ns() - data['stamp_ns'] < 6_000_000_000
        data['streams_fresh'] = data['streams_fresh'] and data['monitor_fresh']
        return data

    code = 0
    try:
        if a.existing_stack:
            start('record', ['bash', str(tools / 'record-drive.sh'), str(a.output / 'bag')])
            start('monitor', ['bash', str(tools / 'run-recording-monitor.sh'),
                             str(a.output / 'recording-status.json'), str(a.output)])
        else:
            command = ['bash', str(tools / 'start-ground-support.sh'), '--record-all',
                       '--runtime', str(a.output / 'runtime'), '--bag-dir', str(a.output / 'bags')]
            if a.video_ip:
                command += ['--video-ip', a.video_ip]
            start('support', command)
        emit('started', output=str(a.output))
        deadline, heartbeat, next_status = time.monotonic() + a.startup_timeout, time.monotonic(), 0
        ready = False
        # TextIO buffering can hide a STOP behind a HEARTBEAT. Read the fd directly.
        pending = b''
        while not stopped:
            now = time.monotonic()
            readable, _, _ = select.select([sys.stdin.fileno()], [], [], .2)
            if readable:
                data = os.read(sys.stdin.fileno(), 4096)
                if not data:
                    state['stop_reason'] = 'ssh_stdin_eof'
                    break
                pending += data
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    if line == b'STOP':
                        stopped = True
                        state['stop_reason'] = 'requested'
                    elif line == b'HEARTBEAT':
                        heartbeat = now
            if now - heartbeat > 30:
                raise RuntimeError('Laptop heartbeat lost for 30 seconds')
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError(f'Recording process exited: {child.returncode}; inspect Pi logs')
            if now >= next_status:
                status = snapshot()
                # motor_bench treats output failures as optional, so inspect its recorder
                # through /proc descendants rather than treating the parent as proof.
                bag_files = list(a.output.rglob('*.mcap'))
                recorder_alive = any('rosbag2' in cmd or 'ros2 bag record' in cmd
                                     for cmd in descendant_commands(children[0].pid))
                status['recorder_alive'] = recorder_alive
                status['bag_files'] = [str(f.relative_to(a.output)) for f in bag_files]
                emit('status', **status)
                if status['streams_fresh'] and recorder_alive and any(f.stat().st_size for f in bag_files):
                    if not ready:
                        ready = True
                        state['status'] = 'recording'
                        emit('ready', output=str(a.output))
                elif ready and not recorder_alive:
                    raise RuntimeError('MCAP recorder exited; see Pi recording logs')
                if not ready and now > deadline:
                    raise RuntimeError('Record-all readiness timeout: ToF/camera/IMU/motor or MCAP missing')
                next_status = now + 2
        state['status'] = 'complete' if ready else 'cancelled_before_ready'
    except Exception as exc:
        code = 1
        state.update(status='failed', error=str(exc))
        emit('error', error=str(exc))
    finally:
        for child in reversed(children):
            try:
                stop_process(child)
            except Exception as exc:
                code = 1
                state.update(status='failed', finalization_error=str(exc))
        for log in logs:
            log.close()
        metadata = list(a.output.rglob('metadata.yaml'))
        state.update(end_pi_epoch_ns=time.time_ns(), bag_metadata=[str(f.relative_to(a.output)) for f in metadata])
        if not metadata:
            code = 1
            state.update(status='failed', finalization_error='No finalized bag metadata.yaml')
        (a.output / 'session.json').write_text(json.dumps(state, indent=2))
        emit('finalized', **state)
    return code


def descendant_commands(pid):
    """Include the root (attach mode runs ros2 directly), plus its subprocesses."""
    pending, commands = [pid], []
    while pending:
        current = pending.pop()
        try:
            commands.append(Path(f'/proc/{current}/cmdline').read_bytes().replace(b'\0', b' ').decode())
            pending.extend(int(p) for p in Path(f'/proc/{current}/task/{current}/children').read_text().split())
        except (OSError, ValueError, UnicodeError):
            pass
    return commands


if __name__ == '__main__':
    sys.exit(main())
