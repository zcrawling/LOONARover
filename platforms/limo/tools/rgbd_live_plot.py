#!/usr/bin/env python3
"""Local browser plot of LIMO RGB-D odometry over a read-only SSH subscriber."""
import collections
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REMOTE = '''import json
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from rtabmap_msgs.msg import OdomInfo
rclpy.init()
n=Node("rgbd_remote_plot_observer")
def odom(m):
 p=m.pose.pose.position
 q=m.pose.pose.orientation
 valid=m.pose.covariance[0]<9999 and q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w>0.5
 print(json.dumps(dict(kind="odom",t=m.header.stamp.sec+m.header.stamp.nanosec/1e9,x=p.x,y=p.y,z=p.z,valid=valid)),flush=True)
def info(m):
 print(json.dumps(dict(kind="info",lost=m.lost,inliers=m.inliers)),flush=True)
n.create_subscription(Odometry,"/rgbd/odom",odom,qos_profile_sensor_data)
n.create_subscription(OdomInfo,"/rgbd/odom_info",info,qos_profile_sensor_data)
try:rclpy.spin(n)
except KeyboardInterrupt:pass
finally:n.destroy_node();rclpy.shutdown()
'''
HTML = '''<!doctype html><meta charset="utf-8"><title>LIMO RGB-D odometry</title>
<style>body{background:#101721;color:#e6edf3;font:16px system-ui;margin:28px}h1{font-size:24px}canvas{background:#182333;border-radius:12px;width:100%;height:300px;margin:12px 0}#status{padding:12px;background:#243248;border-radius:8px}.legend{color:#bdc9dc}</style>
<h1>LIMO · RGB-D Odometry</h1><div id="status">연결 중…</div>
<p class="legend">시간별 위치 (m) · <span style="color:#65dbb0">X</span> / <span style="color:#70b9ff">Y</span> / <span style="color:#ffc775">Z</span> · 최근 120초</p><canvas id="time"></canvas>
<p>XY 궤적 (m) · 유효한 추정만 표시</p><canvas id="xy"></canvas>
<script>
function plot(id,series,xlabel,ylabel){const c=document.getElementById(id),d=devicePixelRatio||1,w=c.clientWidth,h=300;c.width=w*d;c.height=h*d;const g=c.getContext('2d');g.scale(d,d);let pts=series.flatMap(s=>s.p.filter(Boolean));if(!pts.length)return;let xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);let a=Math.min(...xs),b=Math.max(...xs),l=Math.min(...ys),u=Math.max(...ys);if(b-a<.02){a-=.01;b+=.01}if(u-l<.02){l-=.01;u+=.01}let pad=(u-l)*.1;l-=pad;u+=pad;const X=x=>60+(x-a)/(b-a)*(w-85),Y=y=>h-35-(y-l)/(u-l)*(h-60);g.font='12px system-ui';g.fillStyle='#bdc9dc';g.strokeStyle='#33435b';for(let i=0;i<5;i++){let v=l+(u-l)*i/4,y=Y(v);g.beginPath();g.moveTo(60,y);g.lineTo(w-25,y);g.stroke();g.fillText(v.toFixed(3),3,y+4)}g.fillText(a.toFixed(1),60,h-12);g.fillText(b.toFixed(1),w-60,h-12);g.fillText(xlabel,w/2,h-10);g.fillText(ylabel,5,14);for(const s of series){g.strokeStyle=s.color;g.lineWidth=2;g.beginPath();let pen=false;for(const p of s.p){if(!p){pen=false;continue}if(pen)g.lineTo(X(p[0]),Y(p[1]));else g.moveTo(X(p[0]),Y(p[1]));pen=true}g.stroke()}}
async function update(){try{const d=await(await fetch('/data')).json(),p=d.points,age=d.age;let last=p.at(-1);document.getElementById('status').textContent=d.error||(!last?'SSH 연결됨 · /rgbd/odom 대기 중 — LIMO에서 카메라와 odometry를 실행하세요':`수신 ${age.toFixed(1)}초 전 · ${age>3?'데이터 끊김':d.lost?'추적 실패':'수신 중'} · inliers ${d.inliers??'-'} · X ${last.x.toFixed(3)} / Y ${last.y.toFixed(3)} / Z ${last.z.toFixed(3)} m`);if(p.length){let t0=p[0].t;plot('time',['x','y','z'].map((k,i)=>({color:['#65dbb0','#70b9ff','#ffc775'][i],p:p.map(v=>v.valid?[v.t-t0,v[k]]:null)})),'시간 (s)','위치 (m)');plot('xy',[{color:'#65dbb0',p:p.map(v=>v.valid?[v.x,v.y]:null)}],'X (m)','Y (m)')}}catch(e){document.getElementById('status').textContent='로컬 서버 연결 끊김'}setTimeout(update,500)}update();
</script>'''

def main():
 import argparse,time,shlex
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--host',default='wego@192.168.0.7')
 parser.add_argument('--port',type=int,default=8767)
 args=parser.parse_args()
 points=collections.deque(maxlen=5000)
 state={'lost':None,'inliers':None,'error':None,'received':None}
 lock=threading.Lock()
 env=os.environ.copy()
 password=env.pop('LIMO_SSH_PASSWORD',None)
 cmd=['ssh','-T','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',args.host,
      "bash -lc "+shlex.quote("source /opt/ros/humble/setup.bash; source ~/loonar_ws/install/setup.bash; python3 -u -c "+shlex.quote(REMOTE))]
 if password:
  env['SSHPASS']=password;cmd=['sshpass','-e']+cmd
 else:cmd[1:1]=['-o','BatchMode=yes']
 process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
 def receive():
  for line in process.stdout:
   try:m=json.loads(line)
   except ValueError:continue
   with lock:
    if m['kind']=='odom':
     if points and m['t']<points[-1]['t']:points.clear()
     points.append(m);state['received']=time.monotonic()
     while points and m['t']-points[0]['t']>120:points.popleft()
    else:state.update(lost=m['lost'],inliers=m['inliers'])
  with lock:state['error']='SSH 연결 종료. 로컬 그래프 프로그램을 다시 실행하세요.'
 def errors():
  for line in process.stderr:print(line.rstrip(),flush=True)
 threading.Thread(target=receive,daemon=True).start()
 threading.Thread(target=errors,daemon=True).start()
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   if self.path=='/data':
    with lock:
     data=dict(points=list(points),lost=state['lost'],inliers=state['inliers'],error=state['error'],age=time.monotonic()-state['received'] if state['received'] else None)
    body=json.dumps(data,allow_nan=False).encode();mime='application/json'
   elif self.path=='/':body=HTML.encode();mime='text/html; charset=utf-8'
   else:self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
 print(f'http://127.0.0.1:{args.port}',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:
  server.server_close();process.terminate()
  try:process.wait(timeout=5)
  except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
