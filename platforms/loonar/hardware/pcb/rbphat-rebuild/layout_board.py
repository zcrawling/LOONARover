#!/usr/bin/env python3
"""Deterministic B3 placement; consumes the archived B2 pre-layout board."""
import json,shutil
from pathlib import Path
import pcbnew as k
P=Path(__file__).resolve().parent;A=P/'artwork';A.mkdir(exist_ok=True)
base=A/'prelayout-b2.kicad_pcb'
if not base.exists():shutil.copy2(P/'rbphat.kicad_pcb',base)
b=k.LoadBoard(str(base));mm=k.FromMM;v=lambda x,y:k.VECTOR2I(mm(x),mm(y))
pos={
'U1':(127,111,0),'R7':(130,113,90),'C1':(123,109.5,0),'C2':(131,109.5,0),'R2':(134,110,90),
'R1':(118,111,0),'C5':(120,114,90),'U2':(123,115,0),'R8':(126,117,90),'C3':(113,118,90),'R3':(118,119,90),'TP1':(108,113,0),
'U3':(108,126,0),'R4':(108,122.5,0),'R5':(112,129,0),'R6':(105,118,90),'C4':(112,125,90),
'J4':(105,142,90),'R300':(110,140,0),'R301':(114,140,0),'R302':(115,143,90),'C300':(118,140,90),
'U300':(123,141,0),'U301':(123,131,180),'R303':(119,134,0),'C301':(119,136,0),'C302':(129,138,90),'C303':(127,132,90),
'U302':(119,124,0),'R304':(124.5,120.8,0),'R305':(124.5,123,0),'C304':(115,125,90),'C305':(124,127,0),
'TP300':(112,145,0),'TP301':(115,136,0),'TP302':(108,131,0),'TP303':(108,147,0),
}
for n,y in [(100,120),(200,140)]:
 pos.update({f'U{n}':(136,y,0),f'U{n+1}':(146,y,0),f'J{2 if n==100 else 3}':(160,y,90),
 f'R{n}':(132,y-3,90),f'R{n+1}':(140,y+1,0),f'R{n+2}':(132,y+3,0),
 f'R{n+3}':(151.4,y+2.6,0),f'R{n+4}':(151.4,y+.9,0),f'R{n+5}':(151.4,y-2.5,0),f'R{n+6}':(151.4,y-.8,0),
 f'R{n+7}':(154.3,y-.2,90),f'R{n+8}':(141,y-5,0),f'TP{n}':(146,y-5,0),
 f'D{n}':(154.3,y+4,180),f'D{n+1}':(154.3,y-4.5,180),f'C{n}':(137,y-3.6,0),f'C{n+1}':(141.2,y-2,90)})
for fp in b.GetFootprints():
 ref=fp.GetReference()
 if ref in pos:
  x,y,a=pos[ref];fp.SetOrientationDegrees(a);fp.SetPosition(v(x,y))
 elif ref!='J1' and not ref.startswith('H'):raise ValueError(ref)
 fp.Value().SetVisible(False)
 r=fp.Reference();r.SetTextSize(v(.8,.8));r.SetTextThickness(mm(.12))
 if ref in pos:
  r.SetTextAngle(k.EDA_ANGLE(0,k.DEGREES_T));x,y,a=pos[ref]
  r.SetPosition(v(x,y-1.65 if ref[0] in 'RC' else y+2.5))
  r.SetVisible(True)
 if ref=='J1':r.SetVisible(False)
# Remove pre-layout annotation only, not board boundary.
for item in list(b.GetDrawings()):
 if isinstance(item,k.PCB_TEXT):b.Remove(item)
# Global fab artwork ID is independent of schematic electrical revision.
k.SaveBoard(str(P/'rbphat.kicad_pcb'),b)
(A/'placement.json').write_text(json.dumps(pos,indent=2)+'\n')
print('Placed',len(pos),'components. Fixed J1 and four holes retained.')
