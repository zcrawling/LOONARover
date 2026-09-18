"""Run a ramp C experiment over SSH and evaluate against AprilTag on this laptop."""
import argparse,base64,csv,datetime,io,json,re,shlex,signal,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from loonar_apriltag.run_distance_test import ROOT,resolve_host,remember_host
from loonar_apriltag.ssh_auth import authenticated
from loonar_apriltag.trial_analysis import clock_probe


def payload():
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for p in (ROOT/'common/ros2/loonar_localization/loonar_localization').glob('*.py'):z.write(p,'loonar_localization/'+p.name)
  for name in ['bridge.py','capture_xyz.cpp']:z.write(ROOT/'tools/cubeeye_ros'/name,'cubeeye/'+name)
  z.write(ROOT/'platforms/limo/tools/run_c_acc_trial.py','run_trial.py')
  z.write(ROOT/'platforms/limo/tools/prepare_primitive_trial.py','prepare_primitive_trial.py')
  z.write(ROOT/'platforms/limo/ros2/loonar_limo_localization/config/slip_contact_shadow.yaml','dr_profile.yaml')
 return base64.b64encode(b.getvalue()).decode()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ip',required=True,help='LIMO IP; SSH user is wego')
 p.add_argument('--tof',action='store_true',help='Record I200DK and STOP-to-STOP ICP test odom too')
 p.add_argument('--dry-run',action='store_true');p.add_argument('--camera',default='/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_E4159DCF-video-index0')
 p.add_argument('--calibration',default=str(ROOT/'config/cameras/c920_20260909_17mm.json'))
 p.add_argument('--forward-axis',choices=['x','y','-x','-y'],default='x');p.add_argument('--tag-size',type=float,default=.15)
 p.add_argument('--focus',type=int);p.add_argument('--no-preview',action='store_true');
 for name,value in [('speed',.25),('ramp',2.5),('cruise',2.),('decel',2.5),('stop',4.)]:p.add_argument('--'+name,type=float,default=value)
 a=p.parse_args()
 if min(a.speed,a.ramp,a.cruise,a.decel,a.stop)<=0:p.error('speed and durations must be positive')
 host=resolve_host(ip=a.ip)
 if a.dry_run:
  print(json.dumps(dict(host=host,speed=a.speed,ramp=a.ramp,cruise=a.cruise,decel=a.decel,stop=a.stop,
                       tof=a.tof,nominal_distance=a.speed*(a.ramp/2+a.cruise+a.decel/2),motion='disabled'),indent=2));return
 auth=authenticated('ssh');scp=authenticated('scp')
 name=datetime.datetime.now().strftime(('slip_' if a.tof else 'c_vision_')+'%Y%m%d_%H%M%S_%f');out=ROOT/'data/apriltag_gt'/name;out.mkdir(parents=True,exist_ok=False)
 remote_dir='/home/wego/odom_tests/'+name
 camera=remote=None;state=dict(status='preparing',host=host,tof=a.tof,profile={k:getattr(a,k) for k in ['speed','ramp','cruise','decel','stop']},remote_trial_path=remote_dir,tag_mount='horizontal at rover centre; forward-axis supplied',camera_is_evaluation_only=True)
 with tempfile.TemporaryDirectory(prefix='loonar-ssh-') as temp:
  options=['-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new','-o','ControlMaster=auto','-o','ControlPersist=120','-o','ControlPath='+temp+'/sock'];ssh=auth+options+[host]
  try:
   subprocess.run(ssh+['true'],check=True);remember_host(host)
   # Upload to an isolated trial bundle, without replacing installed estimator/driver.
   bundle='/tmp/'+name
   unpack=f"import base64,io,zipfile;from pathlib import Path;p=Path({bundle!r});p.mkdir(exist_ok=False);zipfile.ZipFile(io.BytesIO(base64.b64decode({payload()!r}))).extractall(p)"
   subprocess.run(ssh+['python3 -c '+shlex.quote(unpack)],check=True)
   prelude='source /opt/ros/humble/setup.bash; if [[ -f ~/agilex_ws/install/setup.bash ]]; then source ~/agilex_ws/install/setup.bash; fi; if [[ -f ~/loonar_ws/install/setup.bash ]]; then source ~/loonar_ws/install/setup.bash; fi; '
   subprocess.run(ssh+['bash -c '+shlex.quote(prelude+'python3 -c "import scipy,rclpy,message_filters,sensor_msgs_py"')],check=True)
   print('LIMO 센서/encoder/EKF 준비 확인 (주행 명령 없음).',flush=True)
   subprocess.run(ssh+['bash -c '+shlex.quote(prelude+'cd '+shlex.quote(bundle)+'; exec python3 -u prepare_primitive_trial.py')],check=True)
   state['clock_before']=clock_probe(ssh)
   cal=json.loads(Path(a.calibration).read_text())
   cmd=[sys.executable,str(ROOT/'tools/apriltag_gt/gt.py'),'track','--camera',a.camera,'--calibration',a.calibration,'--width',str(cal['width']),'--height',str(cal['height']),'--output',str(out/'camera'),'--tag-size',str(a.tag_size),'--forward-axis',a.forward_axis,'--focus-mode','lock','--time-offset-s','0','--free-motion','--nominal-speed',str(a.speed)]
   if a.focus is not None:cmd+=['--focus',str(a.focus)]
   if a.no_preview:cmd+=['--no-preview']
   with (out/'camera.log').open('w') as clog,(out/'rover.log').open('w') as rlog:
    camera=subprocess.Popen(cmd,stdout=clog,stderr=subprocess.STDOUT)
    print('태그 인식/초점 고정 대기. Ctrl+C로 취소.',flush=True)
    frames=out/'camera/frames.csv';good=0;last=None
    while good<5:
     if camera.poll() is not None:raise RuntimeError('Camera exited: see camera.log')
     if frames.exists():
      with frames.open() as f:rows=list(csv.DictReader(f))
      if rows and rows[-1].get('frame')!=last:
       row=rows[-1];last=row.get('frame');good=good+1 if row.get('valid')=='1' else 0
     time.sleep(.1)
    command=prelude+'cd '+shlex.quote(bundle)+'; exec python3 -u run_trial.py --stdin-stop --dr-profile dr_profile.yaml --output '+shlex.quote(remote_dir)
    if a.tof:command+=' --tof --tof-bridge cubeeye/bridge.py'
    for key in ['speed','ramp','cruise','decel','stop']:command+=' --'+key+' '+shlex.quote(str(getattr(a,key)))
    print('C ramp 주행과 기록 시작. 태그는 평가에만 사용합니다.',flush=True)
    remote=subprocess.Popen(ssh+['bash -c '+shlex.quote(command)],stdin=subprocess.PIPE,stdout=rlog,stderr=subprocess.STDOUT,text=True);state['status']='running'
    log_position=0
    while remote.poll() is None:
     with (out/'rover.log').open() as live:
      live.seek(log_position);chunk=live.read();log_position=live.tell()
     if chunk:print(chunk,end='',flush=True)
     if camera.poll() is not None:raise RuntimeError('Camera program closed; canceling experiment')
     time.sleep(.2)
    state.update(status='complete' if remote.returncode==0 else 'failed',remote_exit_code=remote.returncode)
  except KeyboardInterrupt:state['status']='interrupted'
  except Exception as e:state.update(status='failed',error=str(e));print(str(e),file=sys.stderr)
  finally:
   signal.signal(signal.SIGINT,signal.SIG_IGN)
   if remote and remote.poll() is None:
    try:remote.stdin.write('STOP\n');remote.stdin.flush();remote.wait(timeout=30)
    except Exception as e:state.update(status='stop_unconfirmed',stop_error=str(e))
   if camera and camera.poll() is None:
    time.sleep(1);camera.send_signal(signal.SIGINT)
    try:camera.wait(timeout=10)
    except subprocess.TimeoutExpired:camera.terminate();camera.wait()
   if remote:
    try:
     state['clock_after']=clock_probe(ssh,3)
     state['record_copy_ok']=subprocess.run(scp+options+['-r',host+':'+remote_dir,str(out/'rover')],timeout=120).returncode==0
    except Exception as e:state['copy_error']=str(e)
   (out/'test.json').write_text(json.dumps(state,indent=2))
   trial_file=out/'rover/trial.json'
   if trial_file.exists():
    remote_status=json.loads(trial_file.read_text());state['remote_status']=remote_status
    if remote_status.get('error'):
     state['error']=remote_status['error'];print('LIMO 시험 실패: '+remote_status['error'],file=sys.stderr)
   if state.get('record_copy_ok') and (out/'rover/bag/metadata.yaml').exists() and (out/'camera/frames.csv').exists():
    result=subprocess.run([str(ROOT/'.venv-icp/bin/python'),str(ROOT/'tools/apriltag_gt/compare_c_test.py'),str(out)],check=False)
    state['comparison_exit_code']=result.returncode
   else:
    state['comparison_status']='skipped_no_recorded_bag';print('기록된 bag이 없어 비교 분석을 건너뜁니다.',flush=True)
   (out/'test.json').write_text(json.dumps(state,indent=2))
   subprocess.run(auth+options+['-O','exit',host],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 print('결과:',out);print(json.dumps(state,indent=2))
 if state['status']!='complete' or state.get('comparison_exit_code')!=0:raise SystemExit(1)
if __name__=='__main__':main()
