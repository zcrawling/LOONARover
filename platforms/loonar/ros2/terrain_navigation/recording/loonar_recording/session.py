"""Start recording before producers; stop producers before final MCAP flush."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from .recorder import save_json

HERE = Path(__file__).resolve().parents[1]
NAV = HERE.parent
ROOT = NAV.parents[3]


def snapshot(session, final=False):
    folder = session/'configuration'
    folder.mkdir(exist_ok=True)
    files = [Path.home()/'loonar-motor-bench/control.json', NAV/'terrain.local.yaml',
             Path('/etc/loonar/cpu-layout.json'),
             NAV/'log/auto-runtime.yaml', Path('/etc/loonar/ros.env'),
             Path('/etc/loonar/mcu-sensors.yaml')]
    files += list((NAV/'loonar_bringup/urdf').glob('*'))
    for path in files:
        if path.is_file():
            shutil.copy2(path, folder/path.name)
    if not final:
        paths = list(HERE.rglob('*.py')) + list((NAV/'fly_brain/loonar_fly').glob('*.py'))
        paths += list((NAV/'runtime').glob('*.py'))
        paths += [ROOT/'platforms/loonar/tools/mcu_v2/link.py', ROOT/'platforms/loonar/tools/mcu_v2/backend.py',
                  ROOT/'common/video/camera_ros.py', NAV/'loonar_tof_adapter/scripts/tof_adapter',
                  ROOT/'platforms/loonar/tools/mcu_v2/motor_bench.py']
        for path in paths:
            target = session/'source'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        save_json(session/'source_sha256.json', {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('manual','fly','observe','gcs'), default='manual')
    parser.add_argument('--seconds', type=float, default=0, help='Optional bounded capture; zero means Ctrl+C')
    parser.add_argument('--output', type=Path, help='New session directory')
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error('seconds must be nonnegative')
    session = (args.output or Path.home()/'loonar-bags'/('capture_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    session.mkdir(parents=True, exist_ok=False)
    (session/'raw').mkdir()
    (session/'logs').mkdir()
    env = dict(os.environ, LOONAR_CAPTURE_SESSION=str(session), PYTHONUNBUFFERED='1',
               LOONAR_CAPTURE_ASYNC_CONTROL='1')
    env['PYTHONPATH'] = f'{HERE}:{ROOT}/platforms/loonar/tools:'+env.get('PYTHONPATH','')
    env.update(LOONAR_ROS_SAMPLE_LAUNCHER=str(NAV/'fly_brain/start_ros.sh'),
               LOONAR_FLY_DRIVE='false', LOONAR_FLY_GCS='0', LOONAR_FLY_CAMERA='1', LOONAR_FLY_CAMERA_FPS='5')
    if args.mode == 'gcs':
        env.update(LOONAR_FLY_GCS='1', LOONAR_FLY_DRIVE='true')
    children, logs, forced = [], [], []
    optional_failures = set()
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
        signal.signal(sig,stop)
    def start(name, command):
        log = open(session/'logs'/f'{name}.log','w')
        logs.append(log)
        child = subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        children.append((name,child))
        return child
    def finish(name, child):
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                forced.append(name)
                os.killpg(child.pid,signal.SIGKILL)
                child.wait()
    metadata = dict(start_ns=time.time_ns(), mode=args.mode, session=str(session),
                    camera_requested_fps=5, manual_endpoint='Pi:7443' if args.mode == 'gcs' else 'Pi:7444',
                    ros_domain_id=env.get('ROS_DOMAIN_ID','0'), hardware_motion_started_by_recorder=False)
    save_json(session/'session.json',metadata)
    snapshot(session)
    print(f'CAPTURE DIRECTORY: {session}',flush=True)
    result = None
    try:
        recorder = start('recorder',[sys.executable,'-m','loonar_recording.recorder',str(session)])
        deadline = time.monotonic()+20
        while not (session/'recorder.ready').exists():
            if stopped or recorder.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('recorder startup failed; inspect logs/recorder.log')
            time.sleep(.1)
        journal_writer=start('control-journal',[sys.executable,'-m','loonar_recording.control_journal',str(session)])
        deadline=time.monotonic()+10
        while not (session/'control-journal.ready').exists():
            if stopped or journal_writer.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('control journal startup failed')
            time.sleep(.05)
        if args.mode == 'gcs':
            start('pi-temperature', [sys.executable, str(NAV/'runtime/thermal_sensor.py')])
        if args.mode in ('manual','observe','gcs'):
            command=[sys.executable,'-m','mcu_v2.motor_bench','--ros-samples',
                '--registry',str(Path.home()/'loonar-motor-bench/control.json'),
                '--gateway-bin',str(ROOT/'build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd')]
            if args.mode == 'gcs':
                command += ['--cfs-dir',str(ROOT/'build/gcs-test/cFS/build-native_std/exe/cpu1'),
                    '--payload-device',env.get('PAYLOAD_DEVICE','/dev/serial/by-id/usb-Teensyduino_USB_Serial_21147480-if00')]
            if args.mode == 'manual':
                start('groundlink',[sys.executable,'-m','loonar_recording.proxy'])
                command += ['--cfs-dir',str(ROOT/'build/gcs-test/cFS/build-native_std/exe/cpu1')]
        else:
            command=['bash',str(NAV/'fly_brain/run_pi.sh'),'--drive']
        start('stack',command)
        metadata['capture_started_ns'] = time.time_ns()
        save_json(session/'session.json',metadata)
        print(f'Recording mode={args.mode}. Ctrl+C saves and verifies.',flush=True)
        started, report_at = time.monotonic(), 0
        while not stopped and (not args.seconds or time.monotonic()-started<args.seconds):
            for name, child in children:
                if child.poll() is not None:
                    if name == 'pi-temperature':
                        if name not in optional_failures:
                            print('Pi temperature unavailable; see logs/pi-temperature.log', flush=True)
                            optional_failures.add(name)
                        continue
                    raise RuntimeError(f'{name} exited ({child.returncode}); see logs/{name}.log')
            if time.monotonic()-report_at > 3:
                path=session/'live_status.json'
                if path.exists():
                    status=json.loads(path.read_text())
                    print('RECORD missing='+(','.join(status['missing']) or 'none')+
                          ' stale='+(','.join(status['stale']) or 'none')+
                          f" free={status['free_bytes']/1024**3:.1f}GiB",flush=True)
                report_at=time.monotonic()
            time.sleep(.2)
    finally:
        metadata['capture_stopped_ns'] = time.time_ns()
        # MCU STOP and camera/ToF close occur while the recorder still captures.
        for name, child in reversed(children):
            finish(name,child)
        metadata.update(end_ns=time.time_ns(),forced_termination=forced,
                        exit_codes={n:p.returncode for n,p in children})
        save_json(session/'session.json',metadata)
        runtime=Path.home()/'loonar-motor-bench/runtime'
        for path in runtime.glob('*.log'):
            shutil.copy2(path,session/'logs'/('runtime-'+path.name))
        for path in (NAV/'fly_brain/log/camera.log',NAV/'fly_brain/log/camera.env'):
            if path.exists():
                shutil.copy2(path,session/'logs'/path.name)
        snapshot(session,final=True)
        for log in logs:
            log.close()
        print('Reading back stored MCAP; please wait...',flush=True)
        from .verify import verify
        try:
            result=verify(session)
        except Exception as error:
            save_json(session/'verification.json',dict(ready_for_analysis=False,readback_complete=False,error=str(error)))
            print(f'BAG VERIFICATION FAILED: {error}',flush=True)
        print(f'COPY THIS WHOLE DIRECTORY: {session}',flush=True)
    return 0 if result and result['ready_for_analysis'] and not forced else 2


if __name__ == '__main__':
    raise SystemExit(main())
