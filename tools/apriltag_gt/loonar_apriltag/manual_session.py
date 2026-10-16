"""One attended manual drive: record-all on Pi, raw external video, live GT, Xbox."""
import argparse
import base64
import csv
import datetime
import ipaddress
import json
import math
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time

from .ssh_auth import authenticated
from .trial_analysis import clock_probe
from .session_time import align_session

ROOT = Path(__file__).resolve().parents[3]


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ip', default='10.254.254.3')
    p.add_argument('--password-file', type=Path, default=Path.home()/'.config/loonar/loonar-ssh-password')
    p.add_argument('--remote-root', default='/home/loonar/LOONAR')
    p.add_argument('--remote-output-root', default='/home/loonar/loonar-bags')
    p.add_argument('--output', type=Path)
    p.add_argument('--camera', default='/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_E4159DCF-video-index0')
    p.add_argument('--calibration', type=Path, default=ROOT/'config/cameras/c920_20260909_17mm.json')
    p.add_argument('--tag-size', type=float, default=.15)
    p.add_argument('--tag-id', type=int, default=0)
    p.add_argument('--forward-axis', choices=['x', 'y', '-x', '-y'], default='x')
    p.add_argument('--focus', type=int, help='Fixed camera focus (0..250); otherwise retain current focus')
    p.add_argument('--fps', type=float, default=30)
    p.add_argument('--camera-delay-s', type=float, default=0., help='Measured exposure-to-receipt delay, subtracted from mapped Pi time')
    p.add_argument('--no-preview', action='store_true')
    p.add_argument('--no-controller', action='store_true', help='Record until Ctrl+C/duration; drive with an existing GCS')
    p.add_argument('--controller-device')
    p.add_argument('--existing-stack', action='store_true', help='Attach recorder to an already running full sensor stack; do not start hardware owners')
    p.add_argument('--video-ip', help='Also stream Pi camera to this laptop IPv4 (new stack only)')
    p.add_argument('--duration', type=float, default=0., help='Recording seconds after readiness; 0 until controller quit/Ctrl+C')
    p.add_argument('--startup-timeout', type=float, default=90.)
    p.add_argument('--no-copy', action='store_true', help='Keep finalized bags on Pi; preserve their path in session.json')
    p.add_argument('--dry-run', action='store_true', help='Print plan without SSH, camera, controller, or motion')
    a = p.parse_args(argv)
    try:
        a.ip = str(ipaddress.IPv4Address(a.ip))
        if a.video_ip:
            a.video_ip = str(ipaddress.IPv4Address(a.video_ip))
    except ValueError as exc:
        p.error(str(exc))
    for name in ('fps', 'tag_size', 'startup_timeout'):
        if not math.isfinite(getattr(a, name)) or getattr(a, name) <= 0:
            p.error(f'{name} must be finite and positive')
    for name in ('duration', 'camera_delay_s'):
        if not math.isfinite(getattr(a, name)) or getattr(a, name) < 0:
            p.error(f'{name} must be finite and nonnegative')
    if not 0 <= a.tag_id < 587 or (a.focus is not None and not 0 <= a.focus <= 250):
        p.error('tag-id must be 0..586; focus must be 0..250')
    if a.existing_stack and a.video_ip:
        p.error('--video-ip configures a new stack; omit it with --existing-stack')
    for path in (a.remote_root, a.remote_output_root):
        if not Path(path).is_absolute() or ':' in path or '\n' in path:
            p.error('Remote paths must be absolute paths without colon/newline')
    return a


def backend_state():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(.5)
        sock.connect(str(ROOT/'GCS/.runtime/backend.sock'))
        sock.sendall(b'{"action":"state"}\n')
        with sock.makefile('rb') as stream:
            return json.loads(stream.readline(2_000_000))


def ensure_backend(ip, log):
    try:
        state = backend_state()
    except (OSError, ValueError):
        state = None
    if state is not None:
        if state.get('source') != 'REAL ROVER / '+ip:
            raise RuntimeError('Existing GCS targets another rover; close it before starting this session')
        return None
    return subprocess.Popen(['python3', '-B', '-m', 'webui.server', '--real-host', ip,
        '--config', str(ROOT/'GCS/config/loonar.toml')], cwd=ROOT/'GCS',
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def stop_child(child, timeout=15):
    if child is None or child.poll() is not None:
        return
    child.send_signal(signal.SIGINT)
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        raise RuntimeError('Process required forced shutdown: '+str(child.args))


def remote_command(a, remote_path):
    source = (Path(__file__).with_name('remote_manual.py')).read_bytes()
    code = "import base64;exec(compile(base64.b64decode("+repr(base64.b64encode(source).decode())+"),'remote_manual.py','exec'))"
    args = ['python3', '-u', '-c', code, '--root', a.remote_root, '--output', remote_path,
            '--startup-timeout', str(a.startup_timeout)]
    if a.existing_stack:
        args += ['--existing-stack']
    if a.video_ip:
        args += ['--video-ip', a.video_ip]
    return shlex.join(args)


def main(argv=None):
    a = arguments(argv)
    name = datetime.datetime.now().strftime('loonar_manual_%Y%m%d_%H%M%S_%f')
    out = (a.output or ROOT/'data/apriltag_gt'/name).resolve()
    remote_path = str(Path(a.remote_output_root)/out.name)
    state = dict(schema_version=1, status='preparing', platform='LOONAR', host='loonar@'+a.ip,
        output=str(out), remote_path=remote_path, recording='record-all / MCAP --all',
        camera_delay_s=a.camera_delay_s, motion='existing manual GCS/Xbox only; no experiment publisher',
        camera_timestamp='laptop receipt + measured Pi-minus-laptop offset - camera_delay_s',
        exposure_latency_calibrated=False, existing_stack=a.existing_stack)
    state['camera'] = dict(device=a.camera, calibration=str(a.calibration), fps=a.fps,
                           tag_id=a.tag_id, tag_size_m=a.tag_size, forward_axis=a.forward_axis,
                           fixed_focus=a.focus)
    if a.dry_run:
        print(json.dumps(state, indent=2))
        return 0
    if not a.no_controller and not sys.stdin.isatty():
        raise RuntimeError('Run in a focused terminal for Xbox, or use --no-controller')
    calibration = json.loads(a.calibration.read_text())
    auth = authenticated('ssh', a.password_file)
    scp = authenticated('scp', a.password_file)
    out.mkdir(parents=True, exist_ok=False)
    camera = remote = controller = backend = None
    files = []
    state_path = out/'session.json'

    def save():
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(state_path)

    def log(name):
        handle = (out/(name+'.log')).open('w')
        files.append(handle)
        return handle

    def check(child, name):
        if child and child.poll() is not None:
            raise RuntimeError(f'{name} exited ({child.returncode}); see {name}.log')

    old = {}
    def interrupted(*_):
        raise KeyboardInterrupt
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        old[sig] = signal.signal(sig, interrupted)
    save()
    with tempfile.TemporaryDirectory(prefix='loonar-manual-') as temp:
        options = ['-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=60', '-o', 'ControlPath='+temp+'/ssh']
        ssh = auth+options+[state['host']]
        clock_file = (out/'clock_samples.jsonl').open('w')
        files.append(clock_file)
        def probe(count):
            sample = clock_probe(ssh, count)
            sample['local_monotonic_ns'] = time.monotonic_ns()
            clock_file.write(json.dumps(sample)+'\n')
            clock_file.flush()
            return sample
        try:
            subprocess.run(ssh+['true'], check=True, timeout=10)
            state['clock_before'] = probe(5)
            offset = state['clock_before']['best']['offset_s']
            save()
            print(f'Session: {out}\nPi: {remote_path}\nClock Pi-PC: {offset:+.6f}s', flush=True)
            remote = subprocess.Popen(ssh+[remote_command(a, remote_path)], stdin=subprocess.PIPE,
                stdout=log('remote'), stderr=subprocess.STDOUT, text=True, start_new_session=True)
            cmd = [sys.executable, str(ROOT/'tools/apriltag_gt/gt.py'), 'track',
                '--camera', a.camera, '--calibration', str(a.calibration),
                '--width', str(calibration['width']), '--height', str(calibration['height']),
                '--fps', str(a.fps), '--output', str(out/'camera'), '--free-motion',
                '--archive-all-frames', '--focus-mode', 'keep', '--tag-id', str(a.tag_id),
                '--tag-size', str(a.tag_size), '--forward-axis', a.forward_axis,
                '--time-offset-s', str(offset-a.camera_delay_s)]
            if a.focus is not None:
                cmd += ['--focus', str(a.focus)]
            if a.no_preview:
                cmd += ['--no-preview']
            camera = subprocess.Popen(cmd, stdout=log('camera'), stderr=subprocess.STDOUT,
                                      start_new_session=True)
            # No tag lock or estimator-bias gate: raw recording is the primary output.
            deadline, position = time.monotonic()+a.startup_timeout+10, 0
            ready = pi_ready = False
            while not ready:
                check(camera, 'camera')
                check(remote, 'remote')
                remote.stdin.write('HEARTBEAT\n'); remote.stdin.flush()
                with (out/'remote.log').open() as stream:
                    stream.seek(position)
                    for line in stream:
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get('event') == 'ready':
                            pi_ready = True
                        if event.get('event') == 'error':
                            raise RuntimeError(event['error'])
                    position = stream.tell()
                archive = out/'camera/video_frames.csv'
                if pi_ready and archive.exists():
                    with archive.open() as stream:
                        ready = next(csv.DictReader(stream), None) is not None
                if time.monotonic() > deadline:
                    raise RuntimeError('Camera/Pi readiness timeout; inspect camera.log and remote.log')
                time.sleep(.2)
            if not a.no_controller:
                backend = ensure_backend(a.ip, log('gcs'))
                deadline = time.monotonic()+15
                while True:
                    check(backend, 'gcs')
                    try:
                        status = backend_state()
                        if status.get('source') != 'REAL ROVER / '+a.ip:
                            raise RuntimeError('GCS target changed')
                        if status.get('connection') == 'CONNECTED':
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError('GCS did not connect to LOONAR')
                    remote.stdin.write('HEARTBEAT\n'); remote.stdin.flush()
                    time.sleep(.2)
                cmd = ['bash', str(ROOT/'GCS/scripts/start_controller.sh'),
                       '--event-log', str(out/'controller.jsonl')]
                if a.controller_device:
                    cmd += ['--device', a.controller_device]
                controller = subprocess.Popen(cmd)
            state.update(status='recording', ready_laptop_epoch=time.time())
            save()
            print('RECORDING: manual driving only. Tag loss does not stop recording. q in GT / controller, or Ctrl+C ends session.', flush=True)
            began = last_probe = time.monotonic()
            while not a.duration or time.monotonic()-began < a.duration:
                check(remote, 'remote')
                if controller and controller.poll() is not None:
                    if controller.returncode:
                        raise RuntimeError(f'Controller exited: {controller.returncode}')
                    break
                if camera.poll() is not None:
                    if camera.returncode:
                        raise RuntimeError(f'Camera exited: {camera.returncode}; see camera.log')
                    break
                check(backend, 'gcs')
                remote.stdin.write('HEARTBEAT\n'); remote.stdin.flush()
                if time.monotonic()-last_probe >= 30:
                    probe(1)
                    last_probe = time.monotonic()
                time.sleep(.2)
            state['status'] = 'complete'
        except KeyboardInterrupt:
            state.update(status='interrupted', stop_reason='operator')
        except Exception as exc:
            state.update(status='failed', error=str(exc))
            print(str(exc), file=sys.stderr)
        finally:
            for sig in old:
                signal.signal(sig, signal.SIG_IGN)
            # Controller STOP precedes recorder finalization; reused GCS is left running.
            for child, label in ((controller, 'controller'), (camera, 'camera')):
                try:
                    stop_child(child)
                except Exception as exc:
                    state.update(status='failed', **{label+'_stop_error': str(exc)})
            if remote:
                try:
                    if remote.poll() is None:
                        remote.stdin.write('STOP\n'); remote.stdin.flush()
                        remote.wait(timeout=100)
                    state['remote_exit_code'] = remote.returncode
                    if remote.returncode:
                        state.update(status='failed', remote_finalization='unconfirmed; inspect Pi session.json')
                except Exception as exc:
                    state.update(status='failed', remote_stop_error=str(exc))
                    try:
                        stop_child(remote, 5)
                    except Exception:
                        pass
                finally:
                    remote.stdin.close()
            try:
                state['clock_after'] = probe(3)
            except Exception as exc:
                state['clock_after_error'] = str(exc)
            if remote and not a.no_copy:
                try:
                    result = subprocess.run(scp+options+['-r', state['host']+':'+remote_path, str(out/'rover')], timeout=600)
                    state['copy_ok'] = result.returncode == 0
                except Exception as exc:
                    state.update(copy_ok=False, copy_error=str(exc))
            else:
                state['copy_status'] = 'kept_on_pi'
            try:
                stop_child(backend)
            except Exception as exc:
                state.update(status='failed', backend_stop_error=str(exc))
            state['ended_laptop_epoch'] = time.time()
            save()
            try:
                state['timing'] = align_session(out)
            except Exception as exc:
                state['alignment_error'] = str(exc)
            save()
            try:
                subprocess.run(auth+options+['-O', 'exit', state['host']],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass  # ControlPersist expires the SSH master even if explicit close fails.
            for handle in files:
                handle.close()
            for sig, handler in old.items():
                signal.signal(sig, handler)
    print('Saved session: '+str(out), flush=True)
    if state.get('copy_ok') is False:
        print('Bag copy failed; original remains on Pi: '+remote_path, file=sys.stderr)
    return 0 if (state['status'] in ('complete', 'interrupted') and
                 'alignment_error' not in state and state.get('copy_ok') is not False) else 1
