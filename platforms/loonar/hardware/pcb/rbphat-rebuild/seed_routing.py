#!/usr/bin/env python3
"""Local ground stitching and short decoupling routes, then export outer-layer router input."""
import math,json,re
from pathlib import Path
import pcbnew as k
P=Path(__file__).resolve().parent;b=k.LoadBoard(str(P/'rbphat.kicad_pcb'));mm=k.FromMM;v=lambda x,y:k.VECTOR2I(mm(x),mm(y));xy=lambda p:(k.ToMM(p.x),k.ToMM(p.y))
fps={f.GetReference():f for f in b.GetFootprints()};pads=[p for f in fps.values() for p in f.Pads()];keep=[];traces=[];vias=[]
def rect(p):
 r=p.GetBoundingBox();return (k.ToMM(r.GetLeft()),k.ToMM(r.GetTop()),k.ToMM(r.GetRight()),k.ToMM(r.GetBottom()))
obs=[(p.GetNetCode(),rect(p)) for p in pads]
def clear(x,y,r,net):
 if not(100.6+r<x<164.4-r and 100.6+r<y<155.4-r):return False
 for hx,hy in [(103.5,103.5),(161.5,103.5),(103.5,152.5),(161.5,152.5)]:
  if math.hypot(x-hx,y-hy)<3.1+r:return False
 for n,(l,t,rr,bb) in obs:
  if n==net:continue
  if math.hypot(max(l-x,0,x-rr),max(t-y,0,y-bb))<r+.205:return False
 for n,vx,vy in vias:
  if n!=net and math.hypot(x-vx,y-vy)<r+.3+.205:return False
 for n,a,c,w in traces:
  if n==net:continue
  dx,dy=c[0]-a[0],c[1]-a[1];u=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy or 1)))
  if math.hypot(x-a[0]-u*dx,y-a[1]-u*dy)<r+w/2+.205:return False
 return True
def pathclear(points,w,net):
 for a,c in zip(points,points[1:]):
  ns=math.ceil(math.dist(a,c)/.05)
  for i in range(ns+1):
   t=i/max(ns,1)
   if not clear(a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t,w/2,net):return False
 return True
def route(points,w,net):
 for a,c in zip(points,points[1:]):
  if math.dist(a,c)<.001:continue
  t=k.PCB_TRACK(b);t.SetStart(v(*a));t.SetEnd(v(*c));t.SetWidth(mm(w));t.SetLayer(k.F_Cu);t.SetNetCode(net);b.Add(t);keep.append(t);traces.append((net,a,c,w))
def via(x,y,net):
 t=k.PCB_VIA(b);t.SetPosition(v(x,y));t.SetWidth(mm(.6));t.SetDrill(mm(.3));t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(net);b.Add(t);keep.append(t);vias.append((net,x,y))
# Each surface ground pad gets a nearby through via; adjoining pads may share a via.
failed=[]
for p in pads:
 if p.GetNetname()!='GND' or p.GetParentFootprint().GetReference()=='J1':continue
 x,y=xy(p.GetPosition());n=p.GetNetCode();done=False
 for vn,vx,vy in vias:
  if vn==n and math.hypot(vx-x,vy-y)<2 and pathclear([(x,y),(vx,vy)],.25,n):route([(x,y),(vx,vy)],.25,n);done=True;break
 if done:continue
 for d in [1.0,1.2,1.5,1.8,2.2]:
  for angle in [0,90,180,270,45,135,225,315]:
   a=math.radians(angle);vx,vy=x+d*math.cos(a),y+d*math.sin(a)
   if clear(vx,vy,.3,n) and pathclear([(x,y),(vx,vy)],.25,n):
    route([(x,y),(vx,vy)],.25,n);via(vx,vy,n);done=True;break
  if done:break
 if not done:failed.append((p.GetParentFootprint().GetReference(),p.GetNumber()))
# Short capacitor-to-load and LM feedback routes, with checked 45-degree paths.
for ref,ic in [('C100','U100'),('C101','U101'),('C200','U200'),('C201','U201'),('C302','U300'),('C303','U301'),('C304','U302'),('C305','U302'),('C4','U3'),('C1','U1'),('C2','U1'),('C5','U2')]:
 p=next(p for p in fps[ref].Pads() if p.GetNumber()=='1');qs=[q for q in fps[ic].Pads() if q.GetNetCode()==p.GetNetCode()]
 for q in qs:
  a=xy(p.GetPosition());c=xy(q.GetPosition());dx,dy=c[0]-a[0],c[1]-a[1];d=min(abs(dx),abs(dy));sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
  for points in [[a,(a[0]+sx*d,a[1]+sy*d),c],[a,(c[0]-sx*d,c[1]-sy*d),c]]:
   if pathclear(points,.25,p.GetNetCode()):route(points,.25,p.GetNetCode());break
# Unbroken internal reference planes. Power routes remain on outer layers.
gnd=b.FindNet('GND')
for layer in [k.In1_Cu,k.In2_Cu]:
 z=k.ZONE(b);z.SetLayer(layer);z.SetNet(gnd);z.SetLocalClearance(mm(.25));z.SetThermalReliefGap(mm(.25));z.SetThermalReliefSpokeWidth(mm(.3));z.SetPadConnection(k.ZONE_CONNECTION_FULL)
 o=z.Outline();o.NewOutline()
 for x,y in [(100.5,100.5),(164.5,100.5),(164.5,155.5),(100.5,155.5)]:o.Append(mm(x),mm(y))
 b.Add(z);keep.append(z)
b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P/'rbphat.kicad_pcb'),b)
k.ExportSpecctraDSN(b,str(P/'artwork/seeded.dsn'))
s=(P/'artwork/seeded.dsn').read_text().replace('(width 200)','(width 250)').replace('(clearance 50 (type smd_smd))','(clearance 200 (type smd_smd))')
# Explicit wide supply net class (fine IC escapes are manually seeded at 0.25mm).
power=['+3V3_PI','+3V3_ANA','+3V3_RS','/ANA_FEED','/CTRL full-duplex RS-422/CTRL_VCC','/PAY full-duplex RS-422/PAY_VCC']
idx=s.index('(class kicad_default');end=s.index('(circuit',idx);head=s[idx:end]
for n in power:head=head.replace(json.dumps(n) if ' ' in n else n,'')
s=s[:idx]+head+s[end:]
pos=s.index('  (wiring')
s=s[:pos-4]+'    (class Power '+ ' '.join(json.dumps(n) for n in power)+' (circuit (use_via "Via[0-3]_600:300_um")) (rule (width 500) (clearance 200)))\n  )\n'+s[pos:]
(P/'artwork/router.dsn').write_text(s)
(P/'artwork/seed-report.json').write_text(json.dumps({'ground_vias':len(vias),'seed_segments':len(traces),'ground_pads_for_router':failed},indent=2)+'\n')
print('Seeded',len(vias),'ground vias,',len(traces),'tracks; remaining ground pads:',failed)
