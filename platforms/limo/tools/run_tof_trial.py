"""Owned ToF bridge/registration and bounded recorded STOP-to-STOP trial."""
import argparse,datetime,json,os,signal,subprocess,sys,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--distance',type=float,default=.3);p.add_argument('--speed',type=float,default=.1);p.add_argument('--stop-hold',type=float,default=4.);p.add_argument('--observe-only',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
 root=Path(__file__).resolve().parents[3];folder=a.output or Path.home()/'odom_tests'/datetime.datetime.now().strftime('tof_%Y%m%d_%H%M%S');folder.mkdir(parents=True,exist_ok=False);children=[];logs=[]
 def start(args,name):
  f=(folder/(name+'.log')).open('w');logs.append(f);c=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);children.append(c);return c
 try:
  subprocess.run([sys.executable,str(Path(__file__).with_name('prepare_primitive_trial.py'))],check=True)
  names=subprocess.check_output(['ros2','node','list'],text=True)
  if any(n in names.splitlines() for n in ['/loonar_dead_reckoning','/loonar_stop_registration','/cubeeye_i200dk']):raise RuntimeError('Existing DR/ToF test nodes; stop the previous test before starting another')
  bridge=start([sys.executable,str(root/'tools/cubeeye_ros/bridge.py'),'--output',str(folder/'cloud_probe')],'tof')
  reg=start(['ros2','run','loonar_localization','stop_registration','--ros-args','-p','registration_enabled:=true','-p','publish_map_tf:=false'],'icp')
  deadline=time.monotonic()+30
  while not (folder/'cloud_probe/status.json').exists():
   if bridge.poll() is not None or reg.poll() is not None:raise RuntimeError('ToF/ICP startup failed; inspect '+str(folder))
   if time.monotonic()>deadline:raise RuntimeError('No point cloud received')
   time.sleep(.2)
  print('ToF XYZ ready. '+('정지 관측만 실행' if a.observe_only else 'STOP → 직진 → STOP 시험 시작'),flush=True)
  args=[sys.executable,str(Path(__file__).with_name('run_primitive_trial.py')),'--output',str(folder/'rover'),'--distance',str(a.distance),'--speed',str(a.speed),'--stop-hold',str(a.stop_hold),'--tof','--no-stdin-stop']
  if a.observe_only:args+=['--observe-only-seconds','10']
  motion=subprocess.Popen(args,start_new_session=True);children.append(motion)
  code=motion.wait()
  if code:raise RuntimeError('Trial failed with code '+str(code))
  subprocess.run([sys.executable,str(root/'tools/cubeeye_ros/analyze_trial.py'),str(folder)],check=True)
 finally:
  signal.signal(signal.SIGINT,signal.SIG_IGN)
  for c in reversed(children):
   if c.poll() is None:
    os.killpg(c.pid,signal.SIGINT)
    try:c.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(c.pid,signal.SIGTERM);c.wait(timeout=5)
  for f in logs:f.close()
  print('결과: '+str(folder),flush=True)

if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:sys.exit(130)
