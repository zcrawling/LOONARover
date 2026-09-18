#!/usr/bin/env python3
"""Place readable reference labels without masking copper or component outlines."""
from pathlib import Path
import math,json
import pcbnew as k
P=Path(__file__).resolve().parent;b=k.LoadBoard(str(P/'rbphat.kicad_pcb'));mm=k.FromMM;v=lambda x,y:k.VECTOR2I(mm(x),mm(y));keep=[]
def box(item):
 r=item.GetBoundingBox();return tuple(k.ToMM(n) for n in (r.GetLeft(),r.GetTop(),r.GetRight(),r.GetBottom()))
def overlaps(a,c,g=.18):return not(a[2]+g<c[0] or c[2]+g<a[0] or a[3]+g<c[1] or c[3]+g<a[1])
obs=[];bodies={}
for f in b.GetFootprints():
 f.Reference().SetVisible(False);f.Value().SetVisible(False)
 if f.GetReference()=='J1':continue
 for p in f.Pads():obs.append(box(p))
 cr=[]
 for g in f.GraphicalItems():
  if g.GetLayer()==k.F_SilkS:obs.append(box(g))
  if g.GetLayer()==k.F_CrtYd:cr.append(box(g))
 if cr:
  rect=(min(r[0] for r in cr),min(r[1] for r in cr),max(r[2] for r in cr),max(r[3] for r in cr));bodies[f.GetReference()]=rect;obs.append(rect)
# Reserve top header pin/tail region including both mask rows.
obs.append((105,100,159.5,108));labels=[]
def valid(bb):
 if not(100.8<bb[0] and bb[2]<164.2 and 100.8<bb[1] and bb[3]<155.2):return False
 return not any(overlaps(bb,r) for r in obs)
def add(text,x,y,size=1):
 t=k.PCB_TEXT(b);t.SetText(text);t.SetLayer(k.F_SilkS);t.SetTextSize(v(size,size));t.SetTextThickness(mm(.13));t.SetPosition(v(x,y));b.Add(t);keep.append(t);obs.append(box(t));labels.append({'text':text,'x':x,'y':y});return t
# User-facing identification and connector polarity.
add('RBPHAT XA B4',114,109.2,.9);add('H16 / GAP19',144,151,.9)
add('CTRL',145,109.5,1);add('PAYLOAD',145,130,1)
add('BAT 0-12.6V',111,134,.9);add('CHASSIS',144,153.5,.9)
# References prioritized by package, then passive. Search nearest free space.
fs=sorted([f for f in b.GetFootprints() if f.GetReference() in bodies and not f.GetReference().startswith('H')],key=lambda f:(0 if f.GetReference()[0] in 'UJDT' or f.GetReference()=='SH1' else 1,f.GetReference()))
for f in fs:
 ref=f.GetReference();r=f.Reference();r.SetTextSize(v(.8,.8));r.SetTextThickness(mm(.12));r.SetTextAngle(k.EDA_ANGLE(0,k.DEGREES_T))
 x,y=k.ToMM(f.GetPosition().x),k.ToMM(f.GetPosition().y);l,t,rr,bb=bodies[ref]
 candidates=[]
 for dx in [0,-.8,.8,-1.6,1.6,-2.4,2.4,-3.2,3.2,-4,4,-5,5,-6,6]:
  for d in [.8,1.2,1.6,2,2.6,3.2,4,5,6,7]:candidates.extend([(x+dx,t-d),(x+dx,bb+d),(l-d,y+dx),(rr+d,y+dx)])
 candidates.sort(key=lambda p:math.hypot(p[0]-x,p[1]-y))
 for cx,cy in candidates:
  r.SetPosition(v(cx,cy));rb=box(r)
  if valid(rb):r.SetVisible(True);obs.append(rb);labels.append({'text':ref,'x':cx,'y':cy});break
 else:
  r.SetTextAngle(k.EDA_ANGLE(90,k.DEGREES_T))
  for cx,cy in candidates:
   r.SetPosition(v(cx,cy));rb=box(r)
   if valid(rb):r.SetVisible(True);obs.append(rb);labels.append({'text':ref,'x':cx,'y':cy});break
  else:raise RuntimeError('No silk position '+ref)
# Header pin 1 mark is on front: the socket itself is underneath.
t=add('1',108.37,107.9,.8)
k.SaveBoard(str(P/'rbphat.kicad_pcb'),b);(P/'artwork/silk-labels.json').write_text(json.dumps(labels,indent=2)+'\n');print('Placed',len(labels),'labels')
