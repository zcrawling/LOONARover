from pathlib import Path
import json,shutil,urllib.request
from sexpr import *
P=Path(__file__).resolve().parent;o=json.loads((P/'component_overrides.json').read_text())
for ref,n in [('J2',6),('J3',6),('J4',2)]:
 name=f'JST_XA_S{n:02}B-XASK-1_1x{n:02}_P2.50mm_Horizontal';fp=parse((Path('/usr/share/kicad/footprints/Connector_JST.pretty')/(name+'.kicad_mod')).read_text());local=f'XA_S{n:02}B_Horizontal';fp[1]=q(local)
 for m in children(fp,'model'):
  src=Path(unq(m[1]).replace('${KICAD10_3DMODEL_DIR}','/usr/share/kicad/3dmodels'));dst=P/'models'/src.name
  if src.exists():shutil.copy2(src,dst)
  else:
   dst=P/'models'/f'XA_horizontal_{n}_envelope.wrl'
   def box(cx,cy,cz,sx,sy,sz):
    t=[v/2.54 for v in [cx,cy,cz,sx,sy,sz]]
    return f'Transform {{ translation {t[0]} {t[1]} {t[2]} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor 0.85 0.85 0.8 }} }} geometry Box {{ size {t[3]} {t[4]} {t[5]} }} }} ] }}\n'
   dst.write_text('#VRML V2.0 utf8\n# Nominal XA horizontal body envelope, not contact geometry.\n'+box((n-1)*1.25,-2.9,3.8,(n-1)*2.5+5,12.6,7.6))
  m[1]=q('${KIPRJMOD}/models/'+dst.name)
 (P/'RBPHAT.pretty'/(local+'.kicad_mod')).write_text(emit(fp)+'\n')
 mpn='S06B-XASK-1(LF)(SN)' if n==6 else 'S02B-XASS-1(LF)(SN)'
 o[ref]={'value':mpn.split('(')[0],'mpn':mpn,'footprint':'RBPHAT:'+local,'datasheet':'https://www.jst-mfg.com/product/pdf/eng/eXA-WB.pdf'}
for r in ['R107','R207']:o[r]['value']='120R / fitted'
o['SH1']={'value':'CHASSIS / M3 ring terminal','mpn':'PCB chassis lug / M3 hardware','footprint':'RBPHAT:Chassis_M3_Plated','datasheet':''}
(P/'RBPHAT.pretty/Chassis_M3_Plated.kicad_mod').write_text('(footprint "Chassis_M3_Plated" (version 20260206) (generator pcbnew) (layer "F.Cu") (attr through_hole exclude_from_pos_files exclude_from_bom) (property "Reference" "SH1" (at 0 -4.8) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15)))) (property "Value" "M3 CHASSIS" (at 0 4.8) (layer "F.Fab") (effects (font (size 1 1)))) (fp_circle (center 0 0) (end 4.2 0) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd")) (pad "1" thru_hole circle (at 0 0) (size 6.4 6.4) (drill 3.2) (layers "*.Cu" "*.Mask")))\n')
(P/'component_overrides.json').write_text(json.dumps(o,indent=2)+'\n')
p=P/'generate_schematic.py';s=p.read_text().replace("'GH5'","'XA6'").replace("['TX+','TX-','RX+','RX-','GND']","['TX+','TX-','RX+','RX-','GND','SHIELD']")
s=s.replace("5:'GND'},'BM05B", "5:'GND',6:'CHASSIS'},'BM05B")
s=s.replace("'120R / DNP',355,112,n('RX+'),n('RX-'),True","'120R / fitted',355,122,n('RX+'),n('RX-'),False")
s=s.replace("'GND','POWER_GOOD'","'CHASSIS','GND','POWER_GOOD'")
s=s.replace("'Fit local 120R", "'Fit local 120R")
s=s.replace('Fit local 120R only when this board is the RX endpoint.','Local 120R fitted. Pin 6 SHIELD -> isolated CHASSIS lug SH1.')
s=s.replace("for i,net in enumerate(['+3V3_PI','GND','ANA_FEED']):", "s.comp('SH1','TP','CHASSIS / M3 ring terminal',365,250,{1:'CHASSIS'})\nfor i,net in enumerate(['+3V3_PI','GND','ANA_FEED']):")
s=s.replace('rev "B2"','rev "B4"').replace('16mm body', '16mm body')
p.write_text(s)
p=P/'validate_schematic.py';s=p.read_text().replace("assert sum(c['dnp'] for c in components)==2","assert sum(c['dnp'] for c in components)==0\nsame(('J2',6),('J3',6),('SH1',1));assert actual[('SH1','1')]!=actual[('J1','6')]")
p.write_text(s)
