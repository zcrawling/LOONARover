#!/usr/bin/env python3
"""Independent assertions for the saved B4 layout and manufacturing handoff."""
import json,math,csv,collections,hashlib
from pathlib import Path
from sexpr import *
P=Path(__file__).resolve().parent;b=parse((P/'rbphat.kicad_pcb').read_text());cs=json.loads((P/'components.json').read_text());erc=json.loads((P/'validation/validation.json').read_text());drc=json.loads((P/'artwork/final-drc.json').read_text())
assert erc['erc_errors']==erc['erc_warnings']==0
assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
fps={unq(next(p[2] for p in children(f,'property') if unq(p[1])=='Reference')):f for f in children(b,'footprint')};assert len(fps)==77
nn={};checked=0
for c in cs:
 f=fps[c['reference']];assert unq(f[1])==c['footprint'];x,y=map(float,child(f,'at')[1:3]);assert 100<x<165 and 100<y<156
 assert unq(child(f,'layer')[1])==('B.Cu' if c['reference']=='J1' else 'F.Cu')
 pp={unq(p[1]):p for p in children(f,'pad')}
 for pin,net in c['pins'].items():
  p=pp[pin];n=unq(child(p,'net')[1]);nn[(c['reference'],pin)]=n
  assert (n.startswith('unconnected-') if net is None else n.split('/')[-1]==net),(c['reference'],pin,net,n)
  checked+=1
assert checked==243
for r in ['U1','U2']:assert nn[r,'3']==nn[r,'6'] and nn[r,'1']!=nn[r,'6']
assert nn['U302','1']!=nn['U302','8'];assert nn['U300','2']!=nn['U300','3']
for pin in ['2','4','27','28']:assert nn['J1',pin].startswith('unconnected-')
assert nn['J2','6']==nn['J3','6']==nn['SH1','1']=='CHASSIS'
assert nn['J2','5']==nn['J3','5']=='GND'
assert not any(c['dnp'] for c in cs)
for r in ['J2','J3']: assert len([p for p in children(fps[r],'pad') if unq(p[1])])==6
segs=children(b,'segment');vias=children(b,'via');assert segs and vias
lengths=collections.defaultdict(float);layerlength=collections.defaultdict(float)
for s in segs:
 n=unq(child(s,'net')[1]);assert n in nn.values() and not n.startswith('unconnected-');w=float(child(s,'width')[1]);assert .2<=w<=.5
 layer=unq(child(s,'layer')[1]);assert layer in ['F.Cu','B.Cu']
 le=math.dist(list(map(float,child(s,'start')[1:])),list(map(float,child(s,'end')[1:])));lengths[n]+=le;layerlength[layer]+=le
for vi in vias:assert float(child(vi,'size')[1])==.6 and float(child(vi,'drill')[1])==.3
zones=[z for z in children(b,'zone') if not child(z,'keepout')];assert len(zones)==2
for z in zones:assert unq(child(z,'net')[1])=='GND' and len(children(z,'filled_polygon'))==1
assert {unq(child(z,'layer')[1]) for z in zones}=={'In1.Cu','In2.Cu'}
rows=list(csv.DictReader((P/'manufacturing/assembly/top-placement.csv').open()));assert len(rows)==61
assert {r['Ref'] for r in rows}=={c['reference'] for c in cs if not c['dnp'] and not c['reference'].startswith(('TP','SH','J'))}
assert all(r['Side']=='top' for r in rows)
for ext in ['gtl','g1','g2','gbl','gts','gbs','gto','gbo','gm1']:assert len(list((P/'manufacturing/gerber').glob('*.'+ext)))==1
for kind in ['PTH','NPTH']:assert (P/f'manufacturing/gerber/rbphat-{kind}.drl').stat().st_size>100
report={'pcb_sha256':hashlib.sha256((P/'rbphat.kicad_pcb').read_bytes()).hexdigest(),'revision':'B4','schematic_pin_assignments_checked':checked,'erc_errors':0,'erc_warnings':0,'drc_violations':0,'unconnected_items':0,'schematic_parity_issues':0,'circuit_items':73,'mounting_holes':4,'fitted_smd_parts':61, 'fitted_top_pth_connectors':3,'fitted_bottom_pth_socket':1,'dnp_parts':[],'testpoints':7,'track_segments':len(segs),'through_vias':len(vias),'trace_width_mm':[min(float(child(s,'width')[1]) for s in segs),max(float(child(s,'width')[1]) for s in segs)],'routing_layer_length_mm':dict(layerlength),'net_copper_length_mm':{n:round(le,4) for n,le in sorted(lengths.items())},'ground_planes':{'In1.Cu':'single connected filled island','In2.Cu':'single connected filled island'},'drc_ignored_checks':drc['ignored_checks'],'limitations':['CAD checks establish no detected layout/connectivity violations; no physical prototype or EMC testing performed.','2 Mbps target; no controlled-impedance fabrication requirement or 50 Mbps qualification claimed.','Nominal 19 mm mechanical stack needs first-article fit verification.']}
(P/'artwork/validation.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS B4: ERC 0/0, DRC 0, unrouted 0, parity 0, 243 pin assignments, 61 SMD + 4 connectors')
