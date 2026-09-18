#!/usr/bin/env python3
"""Route outstanding power connections on a conservative 50um occupancy grid."""
import json,math,heapq,uuid
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
from sexpr import *
P=Path(__file__).resolve().parent;b=parse((P/'rbphat.kicad_pcb').read_text());pads=json.loads((P/'artwork/pad-geometry.json').read_text());drc=json.loads((P/'artwork/width-drc.json').read_text())
step=.05;nx=1301;ny=1121
xs=100+np.arange(nx)*step;ys=100+np.arange(ny)*step
lid={'F.Cu':0,'B.Cu':1}
def mask_shape(mask,bounds,fn):
 l,t,r,bb=bounds;ix0=max(0,int((l-100)/step)-1);ix1=min(nx,int((r-100)/step)+2);iy0=max(0,int((t-100)/step)-1);iy1=min(ny,int((bb-100)/step)+2)
 if ix1<=ix0 or iy1<=iy0:return
 X,Y=np.meshgrid(xs[ix0:ix1],ys[iy0:iy1]);mask[iy0:iy1,ix0:ix1]|=fn(X,Y)
def circle(m,x,y,r):mask_shape(m,(x-r,y-r,x+r,y+r),lambda X,Y:(X-x)**2+(Y-y)**2<=r*r)
def line(m,a,c,r):
 dx,dy=c[0]-a[0],c[1]-a[1];den=dx*dx+dy*dy
 def f(X,Y):
  u=np.clip(((X-a[0])*dx+(Y-a[1])*dy)/(den or 1),0,1);return (X-a[0]-u*dx)**2+(Y-a[1]-u*dy)**2<=r*r
 mask_shape(m,(min(a[0],c[0])-r,min(a[1],c[1])-r,max(a[0],c[0])+r,max(a[1],c[1])+r),f)
def occupancy(net):
 occ=np.zeros((2,ny,nx),dtype=bool)
 if net!='CHASSIS':
  for z in range(2):circle(occ[z],132,151,4.0)
 for p in pads:
  if p['net']==net:continue
  l,t,r,bb=p['bbox']
  for z in p['layers']:mask_shape(occ[z],(l,t,r,bb),lambda X,Y:(X>=l)&(X<=r)&(Y>=t)&(Y<=bb))
 for s in children(b,'segment'):
  if unq(child(s,'net')[1])==net:continue
  z=lid.get(unq(child(s,'layer')[1]));
  if z is not None:line(occ[z],list(map(float,child(s,'start')[1:])),list(map(float,child(s,'end')[1:])),float(child(s,'width')[1])/2)
 for vi in children(b,'via'):
  if unq(child(vi,'net')[1])==net:continue
  x,y=map(float,child(vi,'at')[1:3]);r=float(child(vi,'size')[1])/2
  for z in range(2):circle(occ[z],x,y,r)
 for z in range(2):
  for x,y in [(103.5,103.5),(161.5,103.5),(103.5,152.5),(161.5,152.5)]:circle(occ[z],x,y,2.9)
  occ[z,:7,:]=True;occ[z,-7:,:]=True;occ[z,:,:7]=True;occ[z,:,-7:]=True
 dist=np.array([distance_transform_edt(~o)*step for o in occ]);return dist>=.335, np.min(dist,axis=0)>=.535
moves=[(1,0,1),(-1,0,1),(0,1,1),(0,-1,1),(1,1,1.4142),(1,-1,1.4142),(-1,1,1.4142),(-1,-1,1.4142)]
def astar(a,c,valid,vm):
 start=(za,round((a[1]-100)/step),round((a[0]-100)/step));end=(zc,round((c[1]-100)/step),round((c[0]-100)/step));ez,ey,ex=end
 def h(p):z,y,x=p;dx,dy=abs(x-ex),abs(y-ey);return max(dx,dy)+.4142*min(dx,dy)+(0 if z==ez else 100)
 assert valid[start] and valid[end],('blocked endpoint',a,c,valid[start],valid[end])
 pq=[(h(start),0,start)];best={start:0};prev={}
 while pq:
  _,cost,p=heapq.heappop(pq)
  if cost!=best.get(p):continue
  if p==end:
   out=[p]
   while p!=start:p=prev[p];out.append(p)
   return out[::-1]
  z,y,x=p
  for dx,dy,dc in moves:
   yy,xx=y+dy,x+dx
   if not(0<=xx<nx and 0<=yy<ny) or not valid[z,yy,xx]:continue
   if dx and dy and not(valid[z,y,xx] and valid[z,yy,x]):continue
   n=(z,yy,xx);nc=cost+dc
   if nc<best.get(n,1e20):best[n]=nc;prev[n]=p;heapq.heappush(pq,(nc+h(n),nc,n))
  if vm[y,x]:
   n=(1-z,y,x);nc=cost+100
   if nc<best.get(n,1e20):best[n]=nc;prev[n]=p;heapq.heappush(pq,(nc+h(n),nc,n))
 raise RuntimeError('No route')
def track(a,c,layer,net):
 if math.dist(a,c)<1e-6:return
 b.append(parse(f'(segment (start {a[0]} {a[1]}) (end {c[0]} {c[1]}) (width 0.2) (layer {q(layer)}) (net {q(net)}) (uuid {q(uuid.uuid4())}))'))
report=[]
for conn in drc['unconnected_items']:
 items=conn['items'];net=items[0]['description'].split('[')[1].split(']')[0];a=tuple(items[0]['pos'][k] for k in ['x','y']);c=tuple(items[1]['pos'][k] for k in ['x','y'])
 za=1 if 'on B.Cu' in items[0]['description'] else 0;zc=1 if 'on B.Cu' in items[1]['description'] else 0
 valid,vm=occupancy(net);path=astar(a,c,valid,vm)
 # Compress same-direction grid edges while retaining layer transitions.
 compressed=[path[0]];prevdir=None
 for i in range(1,len(path)):
  dr=tuple(path[i][j]-path[i-1][j] for j in range(3))
  if prevdir is not None and dr!=prevdir:compressed.append(path[i-1])
  prevdir=dr
 compressed.append(path[-1]);pt=lambda p:(round(100+p[2]*step,5),round(100+p[1]*step,5))
 track(a,pt(path[0]),'B.Cu' if za else 'F.Cu',net);nv=0
 for p,t in zip(compressed,compressed[1:]):
  if p[0]==t[0]:track(pt(p),pt(t),'F.Cu' if p[0]==0 else 'B.Cu',net)
  else:
   x,y=pt(p);b.append(parse(f'(via (at {x} {y}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net {q(net)}) (uuid {q(uuid.uuid4())}))'));nv+=1
 track(pt(path[-1]),c,'B.Cu' if zc else 'F.Cu',net);print(net,a,'->',c,'vias',nv,flush=True);report.append({'net':net,'from':a,'to':c,'vias':nv})
(P/'rbphat.kicad_pcb').write_text(emit(b)+'\n');(P/'artwork/finish-connections.json').write_text(json.dumps(report,indent=2)+'\n')
