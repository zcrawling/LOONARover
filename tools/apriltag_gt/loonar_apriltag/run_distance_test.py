"""Integrated camera-distance terminated LIMO experiment. Executing this drives the rover."""
import argparse
import base64
import csv
import datetime
import json
import math
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import tempfile
import re
import ipaddress
from .trial_analysis import clock_probe, analyze
from .ssh_auth import authenticated

ROOT = Path(__file__).resolve().parents[3]
HOST_CONFIG = Path.home()/'.config/loonar/rover-ssh.json'


def resolve_host(host=None, ip=None, config=HOST_CONFIG):
    if ip is not None:
        ipaddress.IPv4Address(ip)
        host='wego@'+ip
    if host is None:
        host=json.loads(config.read_text())['host'] if config.exists() else 'wego@192.168.0.7'
    if not isinstance(host,str) or not re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*',host):
        raise ValueError('Use an IPv4 address or hostname, optionally user@hostname')
    return host if '@' in host else 'wego@'+host


def remember_host(host,config=HOST_CONFIG):
    config.parent.mkdir(parents=True,exist_ok=True)
    temporary=config.with_suffix('.tmp')
    temporary.write_text(json.dumps({'host':host},indent=2)+'\n')
    temporary.replace(config)


def remote_command(distance, speed, name):
    source = (ROOT/'platforms/limo/tools/run_odom_motion_test.py').read_bytes()
    child = 'import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(source).decode())+'),"motion_test.py","exec"))'
    # Remote supervisor owns the process group; stdin STOP/EOF interrupts the
    # existing runner, whose finally block publishes zero and finalizes rosbag.
    supervisor = '''import subprocess,sys,signal,threading,os
p=subprocess.Popen(sys.argv[1:],start_new_session=True,stdin=subprocess.PIPE,text=True)
def stop():
    for line in sys.stdin:
        if line.strip() == 'STOP': break
        try:
            p.stdin.write(line); p.stdin.flush()
        except (OSError,ValueError):return
    if p.poll() is None:
        try:
            p.stdin.write('STOP\\n'); p.stdin.flush(); p.stdin.close()
        except (OSError,ValueError):
            os.killpg(p.pid,signal.SIGINT)
threading.Thread(target=stop,daemon=True).start()
sys.exit(p.wait())
'''
    command = ['python3','-u','-c',supervisor,'python3','-u','-c',child,
               '--linear',str(speed),'--angular','0','--duration',str(distance/speed),
               '--external-stop','--name',name]
    shell = 'source /opt/ros/humble/setup.bash && if [[ -f ~/agilex_ws/install/setup.bash ]]; then source ~/agilex_ws/install/setup.bash; fi && source ~/loonar_ws/install/setup.bash && exec '+shlex.join(command)
    return 'bash -c '+shlex.quote(shell)


def reached(distance, target):
    return math.isfinite(distance) and distance >= target


class TrackingGate:
    """Bounded dropout tolerance and consecutive-frame recovery, independent of ROS."""
    def __init__(self, grace=.3, recovery=3, timeout=5.):
        self.grace,self.recovery,self.timeout=grace,recovery,timeout
        self.good=0
        self.bad_since=None
        self.mode='PAUSE'

    def update(self,valid,now):
        if valid:
            self.good+=1
            if self.good>=self.recovery:
                self.bad_since=None
                self.mode='RESUME'
        else:
            self.good=0
            if self.bad_since is None:self.bad_since=now
        if self.bad_since is not None:
            elapsed=now-self.bad_since
            if elapsed>=self.timeout:return 'STOP'
            if elapsed>=self.grace:self.mode='PAUSE'
        return self.mode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--distance',type=float,help='Positive forward distance in metres, measured by tag')
    p.add_argument('--speed',type=float,default=.05)
    p.add_argument('--settle-seconds',type=float,default=2.,help='Exclude this time after each start/resume from offline C labels only')
    target=p.add_mutually_exclusive_group()
    target.add_argument('--host',help='SSH hostname or user@hostname; overrides saved successful host')
    target.add_argument('--ip',help='Current LIMO IPv4 address on the hotspot (user defaults to wego)')
    p.add_argument('--check-connection',action='store_true',help='Check and remember SSH only; no camera, driver launch, or motion')
    p.add_argument('--camera',default='/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_E4159DCF-video-index0')
    p.add_argument('--calibration',default=str(ROOT/'config/cameras/c920_20260909_17mm.json'))
    p.add_argument('--focus-mode',choices=['lock','keep'],default='lock')
    p.add_argument('--focus',type=int,help='Fixed C920 focus control, 0..250')
    p.add_argument('--tag-size',type=float,default=.15)
    p.add_argument('--tag-id',type=int,default=0)
    p.add_argument('--forward-axis',choices=['x','y','-x','-y'],default='x',help='Current tested mount uses +X; change when mounting changes')
    p.add_argument('--tracking-grace-s',type=float,default=.3)
    p.add_argument('--tracking-timeout-s',type=float,default=5.)
    p.add_argument('--recovery-frames',type=int,default=3)
    p.add_argument('--time-offset-s',type=float,default=0)
    p.add_argument('--output',help='New output directory; default timestamped under data/apriltag_gt')
    p.add_argument('--no-preview',action='store_true')
    a = p.parse_args()
    try:a.host=resolve_host(a.host,a.ip)
    except (ValueError,KeyError,OSError) as error:p.error(str(error))
    print(f'LIMO SSH target: {a.host}',flush=True)
    try:
        ssh_auth=authenticated('ssh')
        scp_auth=authenticated('scp')
    except RuntimeError as error:p.error(str(error))
    if a.check_connection:
        result=subprocess.run(ssh_auth+['-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',a.host,'hostname'],check=False)
        if result.returncode:sys.exit('SSH connection failed; saved target unchanged. No motion started.')
        remember_host(a.host)
        print(f'연결 성공. 다음 실행에도 {a.host} 사용. 주행은 실행하지 않았습니다.')
        return
    if a.distance is None:p.error('--distance is required unless --check-connection is used')
    if not math.isfinite(a.settle_seconds) or a.settle_seconds<0:p.error('settle-seconds must be finite and nonnegative')
    if any(not math.isfinite(v) or v<=0 for v in (a.distance,a.speed,a.tag_size)):
        p.error('distance, speed and tag-size must be positive finite values')
    if not (math.isfinite(a.tracking_grace_s) and math.isfinite(a.tracking_timeout_s) and 0<=a.tracking_grace_s<a.tracking_timeout_s and a.recovery_frames>=1):
        p.error('Require 0 <= tracking-grace-s < tracking-timeout-s and recovery-frames >= 1')
    if a.focus is not None and not 0<=a.focus<=250:p.error('focus must be 0..250')
    cal = json.loads(Path(a.calibration).read_text())
    name = datetime.datetime.now().strftime('tag_%Y%m%d_%H%M%S_%f')
    out = Path(a.output) if a.output else ROOT/'data/apriltag_gt'/name
    out.mkdir(parents=True,exist_ok=False)
    connection = tempfile.TemporaryDirectory(prefix='loonar-ssh-')
    options = ['-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',
               '-o','ControlMaster=auto','-o','ControlPersist=120',
               '-o','ControlPath='+str(Path(connection.name)/'socket')]
    ssh = [*ssh_auth,*options,a.host]
    # Authenticate before the camera begins and before any motion.
    result = subprocess.run(ssh+['true'],check=False)
    if result.returncode:
        connection.cleanup()
        (out/'test.json').write_text(json.dumps(dict(status='connection_failed',host=a.host,
            ssh_exit_code=result.returncode,motion_started=False),indent=2))
        print(f'\nLIMO SSH 연결 실패: {a.host}. 카메라와 주행은 시작하지 않았습니다.\n'
              '노트북을 LIMO와 통신 가능한 네트워크에 연결하고 LIMO의 현재 IP를 확인하세요.\n'
              '주소가 바뀌었다면 --host wego@실제_IP 를 지정하세요.\n'
              f'연결 확인: ssh {shlex.quote(a.host)}\n결과: {out / "test.json"}',file=sys.stderr)
        sys.exit(1)
    remember_host(a.host)
    bootstrap = '''source /opt/ros/humble/setup.bash
source ~/agilex_ws/install/setup.bash
source ~/loonar_ws/install/setup.bash
nodes=$(ros2 node list)
for name in /limo_base_node /loonar_limo_wheel_odometer /ekf_filter_node; do
  count=$(printf '%s\\n' "$nodes" | grep -cx "$name" || true)
  if (( count > 1 )); then
    echo "Duplicate node $name; resolve duplicate launch processes before motion." >&2
    exit 1
  fi
done
if [[ "$nodes" == *"/limo_base_node"* && "$nodes" == *"/loonar_limo_wheel_odometer"* && "$nodes" == *"/ekf_filter_node"* ]]; then
  exit 0
fi
if [[ "$nodes" == *"/limo_base_node"* || "$nodes" == *"/loonar_limo_wheel_odometer"* || "$nodes" == *"/ekf_filter_node"* ]]; then
  echo 'Incomplete existing localization stack; inspect /tmp/loonar-localization.log before retrying.' >&2
  exit 1
fi
if [[ ! -r /dev/ttylimo || ! -w /dev/ttylimo ]]; then
  echo 'MCU port /dev/ttylimo absent or inaccessible; check udev and dialout membership.' >&2
  exit 1
fi
nohup ros2 launch loonar_limo_localization limo_imu_velocity_ekf.launch.py port_name:=ttylimo > /tmp/loonar-localization.log 2>&1 < /dev/null &
'''
    ready = subprocess.run(ssh+['bash -c '+shlex.quote(bootstrap)],check=False)
    if ready.returncode:
        connection.cleanup()
        (out/'test.json').write_text(json.dumps(dict(status='base_setup_failed',motion_started=False),indent=2))
        sys.exit('LIMO base setup failed; no motion started.')
    command = [sys.executable,str(ROOT/'tools/apriltag_gt/gt.py'),'track',
               '--camera',a.camera,'--calibration',a.calibration,'--width',str(cal['width']),
               '--height',str(cal['height']),'--tag-size',str(a.tag_size),'--tag-id',str(a.tag_id),'--forward-axis',a.forward_axis,
               '--time-offset-s',str(a.time_offset_s),'--output',str(out/'camera')]
    command += ['--focus-mode',a.focus_mode,'--nominal-speed',str(a.speed)]
    if a.focus is not None:command += ['--focus',str(a.focus)]
    if a.no_preview:command.append('--no-preview')
    state = dict(target_m=a.distance,speed_mps=a.speed,nominal_duration_s=a.distance/a.speed,
                 status='preparing',host=a.host,stop_distance_m=None,final_distance_m=None,
                 forward_axis=a.forward_axis,tracking_grace_s=a.tracking_grace_s,
                 tracking_timeout_s=a.tracking_timeout_s,recovery_frames=a.recovery_frames,tracking_events=[])
    state['settle_seconds']=a.settle_seconds
    camera = remote = None
    last_distance = None
    tracking_command = None
    gate=TrackingGate(a.tracking_grace_s,a.recovery_frames,a.tracking_timeout_s)
    last_frame=time.monotonic()
    def send_tracking(action):
        nonlocal tracking_command
        if remote is not None and action!=tracking_command:
            remote.stdin.write(action+'\n'); remote.stdin.flush()
            tracking_command=action
            state['tracking_events'].append(dict(monotonic_s=time.monotonic(),action=action))
            print('Tracking: '+action,flush=True)
    try:
        state['clock_before']=clock_probe(ssh)
        (out/'test.json').write_text(json.dumps(state,indent=2))
        with (out/'camera.log').open('w') as clog, (out/'rover.log').open('w') as rlog:
            camera = subprocess.Popen(command,stdout=clog,stderr=subprocess.STDOUT)
            print('Waiting for visible tag; keep rover stationary. Ctrl+C cancels.',flush=True)
            rows_path = out/'camera/frames.csv'
            stream = None
            try:
                while True:
                    if camera.poll() is not None:
                        raise RuntimeError('Camera exited; see camera.log')
                    if stream is None and rows_path.exists():
                        stream = rows_path.open()
                    line = stream.readline() if stream else ''
                    if not line:
                        if remote is not None:
                            if remote.poll() is not None:raise RuntimeError('Remote runner exited; see rover.log')
                            if time.monotonic()-last_frame>a.tracking_grace_s:
                                action=gate.update(False,time.monotonic())
                                send_tracking('PAUSE' if action=='RESUME' else action)
                                if action=='STOP':raise RuntimeError('Camera stream unavailable beyond tracking timeout')
                        time.sleep(.01)
                        continue
                    row = next(csv.reader([line]))
                    if row[0]=='frame':continue
                    last_frame=time.monotonic()
                    valid = row[2]=='1'
                    action=gate.update(valid,last_frame)
                    if not valid:
                        if remote is not None:
                            if remote.poll() is not None:
                                raise RuntimeError('Remote runner exited; see rover.log')
                            send_tracking(action)
                            if action=='STOP':raise RuntimeError('Tracking did not recover: '+row[3])
                        continue
                    last_distance = float(row[7])
                    if remote is None:
                        if action!='RESUME':continue
                        # Only launch after a valid camera reference exists.
                        print(f'Preparing recorder for {a.distance:g} m at {a.speed:g} m/s; remote runner checks driver and sensors before motion.',flush=True)
                        remote = subprocess.Popen(ssh+[remote_command(a.distance,a.speed,name)],stdin=subprocess.PIPE,stdout=rlog,stderr=subprocess.STDOUT,text=True)
                        state['status']='running'
                    if remote.poll() is not None:
                        raise RuntimeError('Remote runner exited; see rover.log')
                    if reached(last_distance,a.distance):
                        state.update(status='target_reached',stop_distance_m=last_distance)
                        break
                    send_tracking(action)
                    if action=='STOP':raise RuntimeError('Tracking recovery timed out')
            finally:
                if stream:stream.close()
    except KeyboardInterrupt:
        state['status']='interrupted'
    except Exception as error:
        state.update(status='failed',error=str(error))
    finally:
        # A second Ctrl+C must not abandon stop delivery and bag finalization.
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        (out/'test.json').write_text(json.dumps(state,indent=2))
        if remote is not None and remote.poll() is None:
            try:
                remote.stdin.write('STOP\n'); remote.stdin.flush(); remote.stdin.close()
                remote.wait(timeout=30)
                state['remote_exit_code']=remote.returncode
            except (OSError,subprocess.TimeoutExpired) as error:
                state['stop_confirmation_error']=str(error)
                state['status']='stop_unconfirmed'
                print('Remote stop not confirmed; check rover directly.',file=sys.stderr)
        if camera is not None:
            time.sleep(2)
            if camera.poll() is None:
                camera.send_signal(signal.SIGINT)
                try:camera.wait(timeout=10)
                except subprocess.TimeoutExpired:camera.terminate(); camera.wait()
            gt = out/'camera/gt.csv'
            if gt.exists():
                with gt.open() as f:
                    samples=list(csv.DictReader(f))
                if samples:
                    state['final_distance_m']=float(samples[-1]['s_m'])
                    state['final_error_m']=state['final_distance_m']-a.distance
        log_path = out/'rover.log'
        if log_path.exists():
            match = re.search(r'^Recording: (/.+)$',log_path.read_text(),re.MULTILINE)
            if match:
                remote_path = match.group(1).strip()
                state['remote_trial_path']=remote_path
                try:
                    transfer = subprocess.run([*scp_auth,*options,'-r',a.host+':'+shlex.quote(remote_path),str(out/'rover')],check=False,timeout=120)
                    state['record_copy_ok']=transfer.returncode==0
                except subprocess.TimeoutExpired:
                    state['record_copy_ok']=False
                    state['record_copy_error']='Copy timeout; original files remain on rover'
        try:state['clock_after']=clock_probe(ssh,3)
        except Exception as error:state['clock_after_error']=str(error)
        (out/'test.json').write_text(json.dumps(state,indent=2))
        if state.get('record_copy_ok') and 'clock_before' in state:
            try:
                state['c_analysis']=analyze(out,a.settle_seconds)
                print(f'C windows saved: {out / "c_windows.csv"}',flush=True)
            except Exception as error:
                state['c_analysis_error']=str(error)
                print(f'Offline C analysis unavailable: {error}; raw recordings retained.',file=sys.stderr)
        subprocess.run(ssh[:-1]+['-O','exit',a.host],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        connection.cleanup()
        (out/'test.json').write_text(json.dumps(state,indent=2))
        print(json.dumps(state,indent=2))
        print(f'Local results: {out}\nRemote bag path is in rover.log (Recording: ...).')
    if state['status']!='target_reached':sys.exit(1)


if __name__=='__main__':main()
