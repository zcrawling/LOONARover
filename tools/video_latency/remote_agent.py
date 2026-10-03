"""SSH stdio RPC agent: synchronized timestamps, bounded sender lifetime, resource samples."""
import json,os,subprocess,sys,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
proc=None; log=None; rows=[]; done=threading.Event()
HZ=os.sysconf('SC_CLK_TCK')

def snap(pid):
    stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    status=Path(f'/proc/{pid}/status').read_text()
    rss=int(next(l.split()[1] for l in status.splitlines() if l.startswith('VmRSS:')))
    cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith(('MemTotal:','MemAvailable:'))}
    return {'wall':time.time(),'mono':time.monotonic(),'ticks':int(stat[11])+int(stat[12]),'rss_kib':rss,'cpu_total':sum(cpu),'cpu_idle':cpu[3]+cpu[4],'temp_c':int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000,'mem_used_kib':mem['MemTotal']-mem['MemAvailable']}

def sample(pid):
    while not done.wait(.5):
        try:rows.append(snap(pid))
        except (OSError,StopIteration):break

def stop():
    global proc,log
    done.set()
    if proc:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    if log:log.close()
    proc=log=None

try:
 for line in sys.stdin:
    receive_us=time.time_ns()//1000
    r=json.loads(line); action=r['action']
    if action=='sync': response={'recv_us':receive_us,'send_us':time.time_ns()//1000}
    elif action=='start':
        stop();rows=[];done.clear()
        name=r['name']; log=(ROOT/(name+'.log')).open('w')
        conversion='' if r.get('nv12') else '! videoconvert ! video/x-raw,format=I420 '
        pipeline=(f'libcamerasrc ! video/x-raw,width={r["width"]},height={r["height"]},framerate=30/1,format=NV12 '
                  '! queue max-size-buffers=2 leaky=downstream '+conversion+
                  f'! x264enc name=enc tune=zerolatency speed-preset=ultrafast threads={r["threads"]} bitrate={r["bitrate"]} key-int-max=30 bframes=0 '
                  '! h264parse config-interval=1 ! mpegtsmux alignment=7 '
                  f'! udpsink host={r["host"]} port={r["port"]} buffer-size=2097152 sync={str(r["sync"]).lower()} async=false')
        proc=subprocess.Popen([str(ROOT/'stamped_sender'),pipeline,str(ROOT/(name+'.csv'))],stdout=log,stderr=log)
        threading.Thread(target=sample,args=(proc.pid,),daemon=True).start()
        response={'pid':proc.pid,'pipeline':pipeline}
    elif action=='status': response={'running':proc is not None and proc.poll() is None}
    elif action=='stop':
        stop();response={'samples':rows,'encode_csv':(ROOT/(r['name']+'.csv')).read_text(),'log':(ROOT/(r['name']+'.log')).read_text()}
    else:response={'error':'unknown action'}
    print(json.dumps(response),flush=True)
finally:stop()
