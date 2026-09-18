"""CubeEye depth preview with a bounded latest-frame buffer and raw snapshots."""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import threading
import time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True,help='SDK release directory')
    p.add_argument('--max-depth',type=int,default=3000,help='Color scale maximum in SDK depth units')
    p.add_argument('--auto-scale',action='store_true',help='Use valid-depth 2nd/98th percentiles for preview only')
    p.add_argument('--seconds',type=float,default=0,help='Stop after N seconds; 0 means until closed')
    p.add_argument('--headless',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'data/cubeeye'/time.strftime('%Y%m%d_%H%M%S'))
    a=p.parse_args()
    if a.max_depth<=0 or a.seconds<0:p.error('Invalid depth scale or duration')
    sdk=a.sdk.resolve();build=ROOT/'build/cubeeye_viewer';build.mkdir(parents=True,exist_ok=True)
    if not (sdk/'include/CubeEye/CubeEyeCamera.h').exists():p.error('SDK release directory not found')
    for usb in Path('/sys/bus/usb/devices').iterdir():
        try:
            if (usb/'idVendor').read_text().strip()!='3674' or (usb/'idProduct').read_text().strip()!='0200':continue
            device=Path(f'/dev/bus/usb/{int((usb/"busnum").read_text()):03d}/{int((usb/"devnum").read_text()):03d}')
            if not os.access(device,os.R_OK|os.W_OK):
                print(f'Authorizing this USB camera for uid {os.getuid()} (system authentication dialog).',flush=True)
                subprocess.run(['pkexec','/usr/bin/setfacl','-m',f'u:{os.getuid()}:rw',str(device)],check=True)
        except FileNotFoundError:continue
    libdirs=[sdk/'lib',sdk/'thirdparty/liblive555/lib/Release',*[d for d in (sdk/'thirdparty').glob('*/lib') if d.parent.name!='python']]
    env=os.environ.copy();env['LD_LIBRARY_PATH']=':'.join(map(str,libdirs))
    binary=build/'capture';src=Path(__file__).with_name('capture.cpp')
    cmd=['/usr/bin/g++','-std=c++17','-O2','-pthread',str(src),'-I'+str(sdk/'include/CubeEye'),'-L'+str(sdk/'lib'),'-lCubeEye',*['-Wl,-rpath-link,'+str(d) for d in libdirs],'-o',str(binary)]
    subprocess.run(cmd,env=env,check=True)
    a.output.mkdir(parents=True,exist_ok=True)
    read_fd,write_fd=os.pipe();latest=[None,0,0.];lock=threading.Lock();errors=[]
    def receive():
        def read_n(stream,n):
            parts=bytearray()
            while len(parts)<n:
                chunk=stream.read(n-len(parts))
                if not chunk:raise EOFError('Camera stream ended')
                parts.extend(chunk)
            return parts
        try:
            with os.fdopen(read_fd,'rb',buffering=0) as stream:
                while True:
                    magic,w,h=struct.unpack('<III',read_n(stream,12))
                    if magic!=0x43554245 or not 0<w*h<=4096*4096:raise ValueError('Invalid frame header')
                    depth=np.frombuffer(read_n(stream,w*h*2),dtype='<u2').reshape(h,w).copy()
                    with lock:latest[:]=[depth,latest[1]+1,time.monotonic()]
        except Exception as e:errors.append(str(e))
    name='CubeEye I200DK - Depth | S: snapshot | Q: quit'
    log=(a.output/'capture.log').open('w')
    child=subprocess.Popen([str(binary),str(write_fd)],env=env,pass_fds=(write_fd,),stdout=log,stderr=log)
    os.close(write_fd);threading.Thread(target=receive,daemon=True).start()
    began=time.monotonic();first=None;shown=0;status={};canvas=None;depth=None
    try:
        if not a.headless:
            cv2.namedWindow(name,cv2.WINDOW_NORMAL);cv2.resizeWindow(name,900,720)
        while not a.seconds or time.monotonic()-began<a.seconds:
            with lock:depth,count,stamp=latest
            if errors or child.poll() is not None:raise RuntimeError(f'{errors}; see {a.output / "capture.log"}')
            if depth is None:
                if time.monotonic()-began>20:raise RuntimeError('No depth frames in 20s; see capture.log')
                time.sleep(.02);continue
            if time.monotonic()-stamp>3:raise RuntimeError('Depth stream stalled for 3s')
            if count!=shown:
                if first is None:first=time.monotonic()
                shown=count;valid=(depth>0)&(depth<65535);values=depth[valid];h,w=depth.shape
                fps=(count-1)/max(.001,time.monotonic()-first)
                center=depth[max(0,h//2-3):h//2+4,max(0,w//2-3):w//2+4];center=center[(center>0)&(center<65535)]
                status=dict(frames=count,width=w,height=h,fps=round(fps,2),valid_percent=round(float(valid.mean()*100),2),center_raw=float(np.median(center)) if len(center) else None,median_raw=float(np.median(values)) if len(values) else None,depth_unit='SDK native U16; verify physical scale with measured target')
                low,high=(np.percentile(values,[2,98]) if a.auto_scale and len(values) else (0,a.max_depth))
                high=max(low+1,high)
                normalized=np.uint8(np.clip((depth.astype(float)-low)/(high-low),0,1)*255)
                color=cv2.applyColorMap(255-normalized,cv2.COLORMAP_TURBO);color[~valid]=0
                cv2.drawMarker(color,(w//2,h//2),(255,255,255),cv2.MARKER_CROSS,18,1)
                canvas=cv2.copyMakeBorder(color,0,75,0,0,cv2.BORDER_CONSTANT,value=(25,25,25))
                cv2.putText(canvas,f'{w}x{h}  {fps:.1f} FPS  valid {status["valid_percent"]:.1f}%',(12,h+25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
                cv2.putText(canvas,f'Center: {status["center_raw"]} raw | scale {low:.0f}..{high:.0f} | S save / Q quit',(12,h+55),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
            if not a.headless:
                cv2.imshow(name,canvas);key=cv2.waitKey(10)&255
                if key in (27,ord('q')) or cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:break
                if key==ord('s'):
                    cv2.imwrite(str(a.output/f'depth_{count:06d}.png'),depth)
                    cv2.imwrite(str(a.output/f'preview_{count:06d}.png'),canvas)
            else:time.sleep(.01)
    finally:
        child.send_signal(signal.SIGINT)
        try:child.wait(timeout=8)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        log.close()
        if depth is not None:cv2.imwrite(str(a.output/'depth_last.png'),depth)
        if canvas is not None:cv2.imwrite(str(a.output/'preview_last.png'),canvas)
        status.update(sdk=str(sdk),capture_exit_code=child.returncode)
        (a.output/'summary.json').write_text(json.dumps(status,indent=2));print(json.dumps(status,indent=2),flush=True)
        if not a.headless:cv2.destroyAllWindows()

if __name__=='__main__':main()
