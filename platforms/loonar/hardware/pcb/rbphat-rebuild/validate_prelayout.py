#!/usr/bin/env python3
"""Check the saved pre-layout artifacts; run after schematic validation and PCB DRC."""
import hashlib,json
from pathlib import Path
from sexpr import parse,child,children,unq
P=Path(__file__).resolve().parent
b=parse((P/'rbphat.kicad_pcb').read_text())
cs=json.loads((P/'components.json').read_text());audit=json.loads((P/'footprint_audit.json').read_text())
drc=json.loads((P/'validation/prelayout-drc.json').read_text())
erc=json.loads((P/'validation/validation.json').read_text())
assert erc['erc_errors']==erc['erc_warnings']==0
assert not drc['violations'] and not drc['schematic_parity']
assert len(drc['unconnected_items'])==161
assert not children(b,'segment') and not children(b,'via')
fps=children(b,'footprint');assert len(fps)==76
byref={unq(next(p[2] for p in children(f,'property') if unq(p[1])=='Reference')):f for f in fps}
models=set();used=set()
for c in cs:
 ref=c['reference'];fp=byref[ref];assert c['mpn'].strip()
 assert unq(fp[1])==c['footprint'],ref
 assert unq(child(fp,'layer')[1])==('B.Cu' if ref=='J1' else 'F.Cu'),ref
 if ref!='J1':assert float(child(fp,'at')[1])>165,ref
 path=P/'RBPHAT.pretty'/(c['footprint'].split(':')[1]+'.kicad_mod');used.add(path)
 local=parse(path.read_text());assert set(c['pins']) <= {unq(p[1]) for p in children(local,'pad')}
 for m in children(local,'model'):
  mp=Path(unq(m[1]).replace('${KIPRJMOD}',str(P)));assert mp.is_file(),mp;models.add(mp)
for i,xy in enumerate([(103.5,103.5),(161.5,103.5),(103.5,152.5),(161.5,152.5)],1):
 f=byref['H'+str(i)];assert tuple(map(float,child(f,'at')[1:3]))==xy
 assert float(child(children(f,'pad')[0],'drill')[1])==2.75
assert len(used)==15
assert len(children(b,'zone'))==4
for z in children(b,'zone'):assert child(z,'keepout') is not None
n_tp=sum(c['reference'].startswith('TP') for c in cs);n_dnp=sum(c['dnp'] for c in cs)
assert (len(cs),n_tp,n_dnp)==(72,7,2)
result={'revision':'B2','status':'pre-layout checks passed; placement and routing not started','components':72,'purchased_fitted_parts':63,'optional_dnp_parts':2,'pcb_testpoints':7,'mounting_holes':4,'local_footprint_types':len(used),'referenced_model_files':len(models),'erc_errors':0,'erc_warnings':0,'drc_violations':0,'schematic_parity_issues':0,'unconnected_items':161,'tracks':0,'vias':0,'socket_body_mm':16,'nominal_board_gap_mm':19,'cooler':'Raspberry Pi official Active Cooler','drc_ignored_checks':drc['ignored_checks'],'limitations':['DRC applies to an unplaced and unrouted board; it is not fabrication sign-off.','Mechanical dimensions are nominal; physical mating and cooling need assembly verification.','Electrical calculations do not establish transient, surge, or EMC qualification.']}
(P/'validation/prelayout-validation.json').write_text(json.dumps(result,indent=2)+'\n')
files=[p for p in P.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.kicad_prl') and p.name!='artifact-sha256.json']
(P/'validation/artifact-sha256.json').write_text(json.dumps({str(p.relative_to(P)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},indent=2)+'\n')
print(json.dumps(result,indent=2))
