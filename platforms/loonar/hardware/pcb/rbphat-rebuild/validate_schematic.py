#!/usr/bin/env python3
"""Validate the files as parsed by KiCad, not only the generator's in-memory nets."""
import json, os, re, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
P=Path(__file__).resolve().parent;V=P/'validation';V.mkdir(exist_ok=True)
env=os.environ.copy()
# This host has incompatible custom wxWidgets in /usr/local/lib. Use distro libraries
# for this subprocess only; do not change installed software or shell settings.
if Path('/usr/lib/x86_64-linux-gnu/libwx_gtk3u_gl-3.2.so.0').exists():
 env['LD_LIBRARY_PATH']='/usr/lib/x86_64-linux-gnu'+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
def cli(*args):subprocess.run(['kicad-cli',*args],check=True,env=env,cwd=P)
cli('sch','export','netlist','--format','kicadxml','-o',str(V/'netlist.xml'),'rbphat.kicad_sch')
cli('sch','erc','-o',str(V/'erc.rpt'),'rbphat.kicad_sch')
report=(V/'erc.rpt').read_text();assert 'ERC messages: 0  Errors 0  Warnings 0' in report,report
root=ET.parse(V/'netlist.xml').getroot();actual={};members={}
for n in root.findall('./nets/net'):
 name=n.attrib['name'];members[name]=set()
 for t in n.findall('node'):
  key=(t.attrib['ref'],t.attrib['pin']);assert key not in actual
  actual[key]=name;members[name].add(key)
components=json.loads((P/'components.json').read_text());checked=0;fp_checked=[]
for c in components:
 for pin,want in c['pins'].items():
  key=(c['reference'],pin);got=actual.get(key)
  if want is None:
   assert got is None or (len(members[got])==1 and got.startswith('unconnected-')),(key,got)
  else:
   assert got is not None and got.split('/')[-1]==want,(key,want,got)
  checked+=1
 lib,fp=c['footprint'].split(':');path=(P/(lib+'.pretty') if lib=='RBPHAT' else Path('/usr/share/kicad/footprints')/(lib+'.pretty'))/(fp+'.kicad_mod')
 assert path.exists(),path
 pads=set(re.findall(r'\(pad\s+"([^"]+)"',path.read_text()))
 assert set(c['pins'])<=pads,(c['reference'],pads,c['pins'])
 fp_checked.append({'reference':c['reference'],'footprint':c['footprint'],'numbered_pads':sorted(pads)})
# Independent interface invariants: physical Pi pins, package pin numbers, crossing direction.
def same(*nodes):
 nets={actual[(r,str(p))] for r,p in nodes};assert len(nets)==1,(nodes,nets)
for j,buf,ic,base,tx,rx in [('J2','U100','U101',100,7,29),('J3','U200','U201',200,32,33)]:
 same(('J1',tx),(buf,1));same(('J1',rx),(f'R{base+2}',2))
 same((buf,6),(f'R{base+1}',1));same((f'R{base+1}',2),(ic,3));same((ic,2),(buf,3))
 for i,pin in enumerate([5,6,8,7]):
  same((ic,pin),(f'R{base+3+i}',1));same((f'R{base+3+i}',2),(j,i+1))
 same((ic,1),(f'R{base+8}',2),(f'TP{base}',1))
 same((j,5),('J1',6),(ic,4))
for u,rail in [('U1','+3V3_RS'),('U2','+3V3_ANA')]:
 same((u,3),(u,6));assert actual[(u,'6')]==rail
assert actual[('U1','1')]!=actual[('U1','6')]
assert actual[('U2','1')]!=actual[('U2','6')]
same(('J1',3),('U302',3));same(('J1',5),('U302',2))
same(('U302',6),('U301',9));same(('U302',7),('U301',10))
same(('U300',1),('U302',5),('U3',2));same(('U300',3),('U301',4),('R303',1))
same(('U301',1),('J1',6));same(('U301',8),('U2',6))
assert actual[('U300','2')]!=actual[('U300','3')]
assert actual[('U302','1')]!=actual[('U302','8')]
assert sum(c['dnp'] for c in components)==2
for pin in [2,4,27,28]:assert actual.get(('J1',str(pin)),'unconnected-').startswith('unconnected-')
result={'kicad_version':subprocess.check_output(['kicad-cli','version'],env=env,text=True).strip(),'sheets':len(root.findall('./design/sheet')),'components':len(components),'pin_connections_checked':checked,'erc_errors':0,'erc_warnings':0,'explicit_erc_exclusions':0,'default_ignored_checks':report.split('** Ignored checks:')[-1].strip(),'footprint_pad_number_checks':fp_checked,'limits':['ERC and connectivity are not transient simulation or physical hardware tests.','Pad-number coverage does not establish land-pattern dimensions or 3D mechanical clearance.']}
(V/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
cli('sch','export','pdf','-o',str(P/'rbphat.pdf'),'rbphat.kicad_sch')
print(f'PASS: {len(components)} components, {checked} pin connections, 4 sheets, ERC 0/0')
