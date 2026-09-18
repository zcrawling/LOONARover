"""LIMO acceleration experiment launcher: prepare, record, run, clean up."""
import argparse,csv,datetime,os,signal,subprocess,sys,time,threading,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name,value in [('speed',.25),('ramp',2.5),('cruise',2.),('decel',2.5),('stop',4.)]:p.add_argument('--'+name,type=float,default=value)
    p.add_argument('--tof',action='store_true')
    p.add_argument('--tof-bridge',type=Path)
    p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--output',type=Path)
    p.add_argument('--dr-profile',type=Path)
    p.add_argument('--stdin-stop',action='store_true')
    a=p.parse_args()
    if min(a.speed,a.ramp,a.cruise,a.decel,a.stop)<=0:p.error('positive arguments required')
    folder=a.output or Path.home()/'odom_tests'/('c_acc_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));folder.mkdir(parents=True,exist_ok=False)
    children=[];logs=[]
    def start(args,name):
        log=(folder/(name+'.log')).open('w');logs.append(log)
        child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child);return child
    status=dict(status='preparing')
    def cancel_on_input():
        sys.stdin.readline()  # STOP or EOF: cleanup the owned process groups.
        os.kill(os.getpid(),signal.SIGINT)
    try:
        if a.stdin_stop:threading.Thread(target=cancel_on_input,daemon=True).start()
        subprocess.run([sys.executable,str(Path(__file__).with_name('prepare_primitive_trial.py'))],check=True)
        names=subprocess.check_output(['ros2','node','list'],text=True).splitlines()
        if a.tof and any(n in names for n in ['/loonar_stop_registration','/cubeeye_i200dk']):
            raise RuntimeError('Existing ToF test nodes; stop the previous ToF test first')
        if names.count('/loonar_dead_reckoning')>1:raise RuntimeError('Duplicate DR nodes')
        if '/odom_c_test_estimator' in names:raise RuntimeError('C estimator is already running')
        if '/loonar_dead_reckoning' not in names:
            profile=a.dr_profile or Path(__file__).resolve().parents[1]/'ros2/loonar_limo_localization/config/slip_contact_shadow.yaml'
            start([sys.executable,'-c','from loonar_localization.ros_nodes import dr_main; dr_main()','--ros-args','--params-file',str(profile)],'dr')
        est=start([sys.executable,'-m','loonar_localization.c_accel_node','--ros-args','-p','acceleration_mode:=static_bias_experiment','-p','output_dir:='+str(folder/'estimate')],'estimator')
        print('정지 상태의 센서와 accel bias 준비 확인. 주행 명령 없음.',flush=True)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            if est.poll() is not None:raise RuntimeError((folder/'estimator.log').read_text())
            file=folder/'estimate/samples.csv'
            if file.exists():
                with file.open() as f:rows=list(csv.DictReader(f))
                if rows and rows[-1].get('bias_ready')=='True' and rows[-1].get('acceleration_valid')=='True' and abs(time.time()-float(rows[-1]['t']))<.3:break
            time.sleep(.2)
        else:raise RuntimeError('No fresh valid stationary bias; inspect '+str(folder))
        print('READY. Results: '+str(folder),flush=True)
        if a.prepare_only:
            status['status']='prepared';print('준비 확인 완료. 주행 명령을 보내지 않았습니다.',flush=True);return
        extra=['/tof/depth/points','/tof/status','/localization/registration','/odom_tof_test'] if a.tof else []
        bag=start(['ros2','bag','record','-o',str(folder/'bag'),'/imu','/wheel/odom','/wheel/odometer','/odometry/filtered','/localization/dr','/localization/state','/odom_c_test','/c_test/phase','/c_test/diagnostics','/cmd_vel','/tf','/tf_static']+extra,'bag')
        time.sleep(2)
        if bag.poll() is not None:raise RuntimeError('Recorder failed; '+str(folder/'bag.log'))
        if a.tof:
            # Recorder precedes registration so the initial anchor diagnostic is preserved.
            bridge_path=a.tof_bridge or Path(__file__).resolve().parents[3]/'tools/cubeeye_ros/bridge.py'
            bridge=start([sys.executable,str(bridge_path),'--output',str(folder/'cloud_probe')],'tof')
            reg=start([sys.executable,'-c','from loonar_localization.ros_nodes import registration_main; registration_main()',
                       '--ros-args','-p','registration_enabled:=true','-p','publish_map_tf:=false'],'icp')
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if bridge.poll() is not None or reg.poll() is not None:raise RuntimeError('ToF/ICP startup failed; inspect tof.log and icp.log')
                try:
                    probe=json.loads((folder/'cloud_probe/status.json').read_text())
                    if probe['valid_points']>=80 and abs(time.time()-probe['host_callback_ns']/1e9)<1:break
                except (OSError,ValueError,KeyError):pass
                time.sleep(.2)
            else:raise RuntimeError('No fresh usable ToF XYZ received; motion not started')
            print('ToF XYZ ready; recording ICP diagnostics and /odom_tof_test.',flush=True)
        args=[sys.executable,'-m','loonar_localization.c_ramp','--execute']
        for key in ['speed','ramp','cruise','decel','stop']:args+=['--'+key,str(getattr(a,key))]
        print('주행 시작: '+str(a.speed)+' m/s ramp profile (constant-attitude assumption).',flush=True)
        motion=subprocess.Popen(args,start_new_session=True);children.append(motion)
        while motion.poll() is None:
            if any(child.poll() is not None for child in children if child is not motion):
                raise RuntimeError('A recording/estimator process exited during trial; inspect logs')
            time.sleep(.2)
        code=motion.returncode
        if code:raise RuntimeError('Motion exited '+str(code))
        status['status']='complete'
    except BaseException as exc:
        status.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc))
        raise
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=5)
        for f in logs:f.close()
        (folder/'trial.json').write_text(json.dumps(status,indent=2))
        print('결과: '+str(folder),flush=True)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Cancelled.',file=sys.stderr);sys.exit(130)
