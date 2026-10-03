"""Real camera + UDP comparison. Reports pre-encoder to complete PPM latency, NOT glass-to-glass."""
import argparse,binascii,csv,io,json,math,os,select,statistics,struct,subprocess,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/video-latency-pi-20260926'
BASE=['ffmpeg','-hide_banner','-loglevel','warning','-nostdin']
PROFILES=[
 dict(name='low1_current',width=640,height=360,bitrate=1000,threads=1,sync=True,low_delay=False),
 dict(name='low1_lowdelay',width=640,height=360,bitrate=1000,threads=1,sync=True,low_delay=True),
 dict(name='low1_directio',width=640,height=360,bitrate=1000,threads=1,sync=True,low_delay=True,directio=True),
 dict(name='low1_nobuffer',width=640,height=360,bitrate=1000,threads=1,sync=True,low_delay=True,nobuffer=True),
 dict(name='low2_lowdelay',width=640,height=360,bitrate=1000,threads=2,sync=True,low_delay=True),
 dict(name='low4_lowdelay',width=640,height=360,bitrate=1000,threads=4,sync=True,low_delay=True),
 dict(name='medium2_lowdelay',width=1280,height=720,bitrate=3000,threads=2,sync=True,low_delay=True),
 dict(name='high4_lowdelay',width=1920,height=1080,bitrate=5000,threads=4,sync=True,low_delay=True),
 dict(name='high4_passthrough',width=1920,height=1080,bitrate=5000,threads=4,sync=True,low_delay=True,passthrough=True),
 dict(name='high4_unsynced',width=1920,height=1080,bitrate=5000,threads=4,sync=False,low_delay=True),
 dict(name='low1_nv12',width=640,height=360,bitrate=1000,threads=1,sync=True,low_delay=True,nv12=True),
 dict(name='medium2_nv12',width=1280,height=720,bitrate=3000,threads=2,sync=True,low_delay=True,nv12=True),
 dict(name='high4_nv12',width=1920,height=1080,bitrate=5000,threads=4,sync=True,low_delay=True,nv12=True),
 dict(name='low2_unsynced',width=640,height=360,bitrate=1000,threads=2,sync=False,low_delay=True),
]
class Remote:
 def __init__(self):
    self.p=subprocess.Popen(['sshpass','-e','ssh','-o','ConnectTimeout=5','loonar@192.168.0.14',
      '. /opt/loonar/current/lib/loonar-camera-env.sh; exec python3 -u /tmp/loonar-video-latency-20260926/remote_agent.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(OUT/'ssh.log').open('a'),text=True)
 def rpc(self,action,**kw):
    self.p.stdin.write(json.dumps(dict(action=action,**kw))+'\n');self.p.stdin.flush()
    if not select.select([self.p.stdout],[],[],15)[0]:raise TimeoutError('SSH RPC timeout')
    line=self.p.stdout.readline()
    if not line:raise RuntimeError('SSH disconnected')
    return json.loads(line)
 def sync(self):
    samples=[]
    for _ in range(25):
      t0=time.time_ns()//1000;r=self.rpc('sync');t3=time.time_ns()//1000
      samples.append(dict(local_us=(t0+t3)/2,offset_us=((r['recv_us']-t0)+(r['send_us']-t3))/2,
                          uncertainty_us=((t3-t0)-(r['send_us']-r['recv_us']))/2))
      time.sleep(.015)
    return dict(best=min(samples,key=lambda x:x['uncertainty_us']),samples=samples)
 def close(self):
    self.p.stdin.close()
    try:self.p.wait(timeout=10)
    except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=5)

def resource(pid):
 s=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
 status=Path(f'/proc/{pid}/status').read_text()
 return dict(mono=time.monotonic(),wall=time.time(),ticks=int(s[11])+int(s[12]),rss_kib=int(next(l.split()[1] for l in status.splitlines() if l.startswith('VmRSS:'))))

def stats(values):
 if not values:return None
 s=sorted(values)
 return dict(n=len(s),mean=statistics.mean(s),p95=s[math.ceil(.95*len(s))-1],maximum=s[-1],minimum=s[0])

def utilization(rows):
 if not rows:return None
 cpu=[(b['ticks']-a['ticks'])/os.sysconf('SC_CLK_TCK')/(b['mono']-a['mono'])*100 for a,b in zip(rows,rows[1:])]
 return dict(cpu_one_core_percent=stats(cpu),rss_mib=stats([r['rss_kib']/1024 for r in rows]),
    temperature_c=stats([r['temp_c'] for r in rows if 'temp_c' in r]),
    system_cpu_percent=stats([100*(1-(b['cpu_idle']-a['cpu_idle'])/(b['cpu_total']-a['cpu_total'])) for a,b in zip(rows,rows[1:]) if 'cpu_idle' in a and b['cpu_total']>a['cpu_total']]))

def barcode(data,w,h,source_width,source_height):
 bw=source_width//128;bh=16*source_width//640;result=bytearray(13)
 x=round((bh/2+.5)*w/source_height-.5)
 for bit in range(104):
    ox=(bit+.5)*bw
    y=round((source_width-1-ox+.5)*h/source_width-.5)
    at=(y*w+x)*3
    if sum(data[at:at+3])>3*127: result[bit//8]|=1<<(7-bit%8)
 if result[0]!=0xa5 or binascii.crc_hqx(result[:11],0xffff)!=int.from_bytes(result[11:],'big'):return None
 return int.from_bytes(result[1:9],'big'),int.from_bytes(result[9:11],'big')

def run_case(remote,config,seconds,host):
 name=config['name']; folder=OUT/name;folder.mkdir(exist_ok=False)
 procs=[];logs=[];frames=[];invalid=[];resources=[];errors=[];stop=threading.Event()
 clock_before=remote.sync();active=False
 try:
    def launch(cmd,**kwargs):
      log=(folder/f'process{len(procs)}.log').open('w');logs.append(log)
      p=subprocess.Popen(cmd,stderr=log,**kwargs);procs.append(p);return p
    record=folder/'record.ts'
    remux=launch(BASE+['-y','-probesize','32768','-analyzeduration','100000','-i','udp://@:15600?fifo_size=8192&overrun_nonfatal=1',
        '-map','0:v:0','-c:v','copy','-f','mpegts',str(record),'-map','0:v:0','-c:v','copy','-f','mpegts','-flush_packets','1','pipe:1'],stdout=subprocess.PIPE)
    decoder=launch(BASE+['-probesize','32768','-analyzeduration','100000']+(['-flags','low_delay'] if config['low_delay'] else [])+(['-avioflags','direct'] if config.get('directio') else [])+(['-fflags','nobuffer'] if config.get('nobuffer') else [])+
      ['-i','pipe:0','-an','-vf','transpose=cclock,scale=960:720:force_original_aspect_ratio=decrease',*(['-fps_mode','passthrough'] if config.get('passthrough') else ['-fpsmax','30']),'-f','image2pipe','-c:v','ppm','pipe:1'],stdin=remux.stdout,stdout=subprocess.PIPE)
    remux.stdout.close()
    def receive():
      try:
       while not stop.is_set():
        magic=decoder.stdout.readline()
        if not magic:break
        if magic.strip()!=b'P6':raise RuntimeError(repr(magic))
        w,h=map(int,decoder.stdout.readline().split());assert decoder.stdout.readline().strip()==b'255'
        size=w*h*3;data=decoder.stdout.read(size)
        received=time.time_ns()//1000
        if len(data)!=size:break
        stamp=barcode(data,w,h,config['width'],config['height'])
        if stamp:frames.append(dict(received_us=received,stamp_us=stamp[0],sequence=stamp[1]))
        else:invalid.append(received)
      except Exception as exc:errors.append(repr(exc))
    thread=threading.Thread(target=receive,daemon=True);thread.start()
    started=remote.rpc('start',**config,host=host,port=15600);active=True
    deadline=time.monotonic()+15
    while not frames:
      if time.monotonic()>deadline or errors or any(p.poll() is not None for p in procs):raise RuntimeError(f'No valid frames {errors}')
      time.sleep(.05)
    start=time.time();end=start+seconds
    while time.time()<end:
      if errors or any(p.poll() is not None for p in procs):raise RuntimeError(f'Receiver failed: {errors}')
      resources.append(dict(wall=time.time(),processes=[resource(p.pid) for p in procs]))
      time.sleep(.5)
    remote_data=remote.rpc('stop',name=name);active=False
    clock_after=remote.sync()
    stop.set()
    for p in procs:p.terminate()
    for p in procs:
      try:p.wait(timeout=4)
      except subprocess.TimeoutExpired:p.kill();p.wait()
    thread.join(timeout=3)
    before,after=clock_before['best'],clock_after['best']
    selected=[f for f in frames if (start+3)*1e6<=f['received_us']<=end*1e6]
    for f in frames:
      ratio=(f['received_us']-before['local_us'])/(after['local_us']-before['local_us'])
      offset=before['offset_us']+(after['offset_us']-before['offset_us'])*ratio
      f['latency_ms']=(f['received_us']-f['stamp_us']+offset)/1000
    encode=list(csv.DictReader(io.StringIO(remote_data.pop('encode_csv'))))
    (folder/'encode.csv').write_text('sequence,stamp_us,encoded_us\n'+''.join(','.join(e[k] for k in ('sequence','stamp_us','encoded_us'))+'\n' for e in encode))
    (folder/'sender.log').write_text(remote_data.pop('log'))
    (folder/'raw.json').write_text(json.dumps(dict(instrument_version=2,config=config,started=started,clock_before=clock_before,clock_after=clock_after,frames=frames,invalid=invalid,resources=resources,remote=remote_data,start=start,end=end),indent=2))
    steady_pi=[r for r in remote_data['samples'] if start+3<=r['wall']-before['offset_us']/1e6<=end]
    steady_local=[r for r in resources if start+3<=r['wall']<=end]
    goodseq=sorted(set(f['sequence'] for f in selected)); gaps=(goodseq[-1]-goodseq[0]+1-len(goodseq)) if goodseq else None
    chosen={f['sequence'] for f in selected}
    enc=[(int(e['encoded_us'])-int(e['stamp_us']))/1000 for e in encode if int(e['sequence']) in chosen]
    summary=dict(name=name,config=config,seconds=seconds,warmup_seconds=3,latency_ms=stats([f['latency_ms'] for f in selected]),
      latency_including_startup_ms=stats([f['latency_ms'] for f in frames if f['received_us']<=end*1e6]),encoder_ms=stats(enc),clock_uncertainty_ms=max(before['uncertainty_us'],after['uncertainty_us'])/1000,
      clock_offset_change_ms=(after['offset_us']-before['offset_us'])/1000,invalid_frames=len(invalid),sequence_gaps=gaps,
      received_fps=len(selected)/(seconds-3),pi=utilization(steady_pi),laptop=[utilization([r['processes'][i] for r in steady_local]) for i in range(2)])
    (folder/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True);return summary
 finally:
    stop.set()
    if active:
      data=remote.rpc('stop',name=name);(folder/'failed_sender.json').write_text(json.dumps(data,indent=2))
    for p in procs:
      if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    for log in logs:log.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=33);parser.add_argument('--profiles',default='all');parser.add_argument('--suffix',default='');parser.add_argument('--host',default='192.168.0.2');parser.add_argument('--reverse',action='store_true');args=parser.parse_args()
 OUT.mkdir(parents=True,exist_ok=True);remote=Remote()
 try:
    for config in (list(reversed(PROFILES)) if args.reverse else PROFILES):
      if args.profiles!='all' and config['name'] not in args.profiles.split(','):continue
      config=dict(config,name=config['name']+args.suffix)
      run_case(remote,config,args.seconds,args.host)
 finally:remote.close()
