#!/usr/bin/env python3
"""Import fixed-placement SES geometry into KiCad 10's string-net file format."""
from pathlib import Path
import uuid
from sexpr import parse,emit,child,children,unq,q
P=Path(__file__).resolve().parent;b=parse((P/'rbphat.kicad_pcb').read_text());s=parse((P/'artwork/routed.ses').read_text());routes=child(s,'routes');res=child(routes,'resolution');assert res[1]=='um';scale=1000*float(res[2])
fps={unq(next(p[2] for p in children(f,'property') if unq(p[1])=='Reference')):f for f in children(b,'footprint')}
for comp in children(child(s,'placement'),'component'):
 for pl in children(comp,'place'):
  at=child(fps[unq(pl[1])],'at');assert abs(float(pl[2])/scale-float(at[1]))<.0001 and abs(-float(pl[3])/scale-float(at[2]))<.0001
nets={unq(child(p,'net')[1]) for f in fps.values() for p in children(f,'pad') if child(p,'net')}
b[:]=[x for x in b if not(isinstance(x,list) and x[0] in ['segment','via'])];nseg=nv=0
for net in children(child(routes,'network_out'),'net'):
 name=unq(net[1]);assert name in nets,name
 for w in children(net,'wire'):
  p=child(w,'path');layer=unq(p[1]);width=float(p[2])/scale;pts=list(map(float,p[3:]));assert len(pts)%2==0
  for i in range(0,len(pts)-2,2):
   b.append(parse(f'(segment (start {pts[i]/scale} {-pts[i+1]/scale}) (end {pts[i+2]/scale} {-pts[i+3]/scale}) (width {width}) (layer {q(layer)}) (net {q(name)}) (uuid {q(uuid.uuid4())}))'));nseg+=1
 for vi in children(net,'via'):
  assert unq(vi[1])=='Via[0-3]_600:300_um'
  b.append(parse(f'(via (at {float(vi[2])/scale} {-float(vi[3])/scale}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net {q(name)}) (uuid {q(uuid.uuid4())}))'));nv+=1
(P/'rbphat.kicad_pcb').write_text(emit(b)+'\n');print('Imported',nseg,'segments;',nv,'vias')
