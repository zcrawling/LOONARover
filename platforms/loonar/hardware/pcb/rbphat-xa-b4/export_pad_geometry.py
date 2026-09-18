import json,pcbnew as k
b=k.LoadBoard('rbphat.kicad_pcb');a=[]
for f in b.GetFootprints():
 for p in f.Pads():
  r=p.GetBoundingBox();a.append({'ref':f.GetReference(),'pin':p.GetNumber(),'net':p.GetNetname(),'bbox':[k.ToMM(x) for x in [r.GetLeft(),r.GetTop(),r.GetRight(),r.GetBottom()]],'layers':[i for i,l in enumerate([k.F_Cu,k.B_Cu]) if p.IsOnLayer(l)]})
open('artwork/pad-geometry.json','w').write(json.dumps(a))
