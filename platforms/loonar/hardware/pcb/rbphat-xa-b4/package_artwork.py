#!/usr/bin/env python3
"""Package the validated native board and its fabrication exports without scratch data."""
import json,hashlib,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent;M=P/'manufacturing'
report=json.loads((P/'artwork/validation.json').read_text())
assert report['pcb_sha256']==hashlib.sha256((P/'rbphat.kicad_pcb').read_bytes()).hexdigest()
def writezip(path,files,root):
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for f in sorted(set(files)):z.write(f,str(f.relative_to(root)))
 with zipfile.ZipFile(path) as z:assert z.testzip() is None
 print(path.name,len(files),'files',path.stat().st_size,'bytes')
fab=[f for f in (M/'gerber').iterdir() if f.suffix not in ['.pdf']]+[M/'FABRICATION_NOTES.md']
writezip(M/'RBPHAT-B4-fabrication.zip',fab,M)
files=[f for f in P.iterdir() if f.is_file() and (f.suffix in ['.kicad_pcb','.kicad_pro','.kicad_sch','.kicad_sym','.kicad_dru','.md','.csv','.json','.py'] or f.name in ['fp-lib-table','sym-lib-table','rbphat.pdf'])]
for d in ['RBPHAT.pretty','models','references']:files.extend(f for f in (P/d).rglob('*') if f.is_file())
for name in ['validation.json','final-drc.json','top-3d.png','copper-layers.pdf','finish-connections.json','placement.json','silk-labels.json']:files.append(P/'artwork'/name)
for name in ['validation.json','erc.rpt','netlist.xml']:files.append(P/'validation'/name)
files.extend(f for f in M.rglob('*') if f.is_file() and f.suffix!='.zip' and f.name!='SHA256.json')
manifest={str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(set(files))}
(M/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n');files.append(M/'SHA256.json')
writezip(M/'RBPHAT-B4-project.zip',files,P)
