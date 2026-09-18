#!/usr/bin/env python3
"""Attach rules, property parity, and mechanical reservations to the starting board."""
import json,uuid,math
from pathlib import Path
from sexpr import parse,emit,child,children,put,unq,q
P=Path(__file__).resolve().parent;f=P/'rbphat.kicad_pcb';b=parse(f.read_text());cs={c['reference']:c for c in json.loads((P/'components.json').read_text())}
for fp in children(b,'footprint'):
 props={unq(p[1]):p for p in children(fp,'property')};ref=unq(props['Reference'][2])
 if ref.startswith('H'):
  put(props['Reference'],'hide','yes')
  put(fp,'attr','board_only','exclude_from_pos_files','exclude_from_bom')
  for pad in children(fp,'pad'):put(pad,'layers',q('*.Cu'),q('*.Mask'))
  continue
 c=cs[ref]
 for key,val in [('MPN',c['mpn']),('Datasheet',c['datasheet'])]:
  if key in props:props[key][2]=q(val)
  else:fp.append(parse(f'(property {q(key)} {q(val)} (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))'))
setup=child(b,'setup');put(setup,'aux_axis_origin',100,100);put(setup,'grid_origin',100,100)
# Engineering starting stack, not a fabricated impedance certificate.
stack='''(stackup (layer "F.SilkS" (type "Top Silk Screen")) (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01)) (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02)) (layer "In1.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 2" (type "core") (thickness 1.04) (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02)) (layer "In2.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 3" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02)) (layer "B.Cu" (type "copper") (thickness 0.035)) (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)) (layer "B.SilkS" (type "Bottom Silk Screen")) (copper_finish "ENIG") (dielectric_constraints no))'''
old=child(setup,'stackup')
if old:setup.remove(old)
setup.append(parse(stack))
# Screw-head reservations: no electrical copper in diameter 6.2 mm, all layers.
for i,(x,y) in enumerate([(103.5,103.5),(161.5,103.5),(103.5,152.5),(161.5,152.5)]):
 pts=' '.join(f'(xy {x+3.1*math.cos(a*math.pi/16):.6f} {y+3.1*math.sin(a*math.pi/16):.6f})' for a in range(32))
 b.append(parse(f'(zone (net 0) (net_name "") (layers "F.Cu" "In1.Cu" "In2.Cu" "B.Cu") (uuid {uuid.uuid4()}) (name "H{i+1}_screw_clearance") (hatch edge 0.5) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (polygon (pts {pts})))'))
# Passive document labels only; no provisional signal routing.
for x,y,text in [(100,160,'RBPHAT B2 / PRE-LAYOUT / H16 SOCKET + 19mm SPACERS'),(100,163,'Pi5 Active Cooler / all circuit components TOP except J1'),(181,59,'UNPLACED COMPONENT PARKING - MOVE INTO BOARD BEFORE ROUTING')]:
 b.append(parse(f'(gr_text {q(text)} (at {x} {y}) (layer "Dwgs.User") (effects (font (size 1 1) (thickness 0.15)) (justify left)))'))
f.write_text(emit(b)+'\n')
pro=json.loads((P/'rbphat.kicad_pro').read_text());pro['board']={'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.2,'min_via_diameter':.6,'min_through_hole_diameter':.3,'min_copper_edge_clearance':.3,'min_hole_clearance':.25,'min_silk_clearance':.1,'min_text_height':.8,'min_text_thickness':.12},'drc_exclusions':[]}}
base={'bus_width':12,'clearance':.2,'diff_pair_gap':.2,'diff_pair_via_gap':.25,'diff_pair_width':.25,'line_style':0,'microvia_diameter':.3,'microvia_drill':.1,'pcb_color':'rgba(0, 0, 0, 0.000)','schematic_color':'rgba(0, 0, 0, 0.000)','track_width':.25,'via_diameter':.6,'via_drill':.3,'wire_width':6}
pro['net_settings']={'classes':[dict(base,name='Default'),dict(base,name='Power',track_width=.5),dict(base,name='RS422',track_width=.25)],'netclass_patterns':[{'netclass':'Power','pattern':'+3V3*'},{'netclass':'RS422','pattern':'*TX+'},{'netclass':'RS422','pattern':'*TX-'},{'netclass':'RS422','pattern':'*RX+'},{'netclass':'RS422','pattern':'*RX-'}]}
(P/'rbphat.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
(P/'rbphat.kicad_dru').write_text('''(version 1)
(rule "Copper clearance" (constraint clearance (min 0.2mm)))
(rule "Track minimum" (constraint track_width (min 0.2mm)))
(rule "Edge copper margin" (constraint edge_clearance (min 0.3mm)))
(rule "Bottom reserved for Pi and cooler"
 (layer "B.Cu")
 (condition "A.Reference != 'J1'")
 (constraint disallow footprint))
(rule "Mounting screw to copper"
 (condition "A.Reference == 'H*' && B.Type != 'Footprint'")
 (constraint hole_clearance (min 1.725mm)))
''')
print('Properties, stackup, screw reservations and design rules saved')
