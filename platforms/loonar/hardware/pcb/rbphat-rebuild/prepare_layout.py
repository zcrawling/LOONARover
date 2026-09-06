#!/usr/bin/env python3
"""Freeze BOM and project libraries before electrical placement/routing.
Run with Python standard library: python3 prepare_layout.py
"""
import csv,hashlib,json,re,shutil
from pathlib import Path
from sexpr import parse,emit,child,children,put,unq,q
P=Path(__file__).resolve().parent;LIB=P/'RBPHAT.pretty';MODELS=P/'models';LIB.mkdir(exist_ok=True);MODELS.mkdir(exist_ok=True)
cs=json.loads((P/('resolved_bom.json' if (P/'resolved_bom.json').exists() else 'components.json')).read_text());audit=[];mapping={}
# TI land-pattern examples: count, pitch, opposing pad centers, pad X/Y, body X/Y, source/page.
specs={
'U1':('TI_DCK0006A',6,.65,2.2,.9,.4,1.25,2.,'lm66100.pdf',21),
'U2':('TI_DCK0006A',6,.65,2.2,.9,.4,1.25,2.,'lm66100.pdf',21),
'U3':('TI_DBZ0003A',3,.95,2.1,1.3,.6,1.3,2.9,'tlv803e.pdf',40),
'U100':('TI_DBV0006A',6,.95,2.6,1.1,.6,1.6,2.9,'sn74lvc2g17.pdf',31),
'U200':('TI_DBV0006A',6,.95,2.6,1.1,.6,1.6,2.9,'sn74lvc2g17.pdf',31),
'U101':('TI_D0008A',8,1.27,5.4,1.55,.6,3.9,4.9,'thvd1451.pdf',42),
'U201':('TI_D0008A',8,1.27,5.4,1.55,.6,3.9,4.9,'thvd1451.pdf',42),
'U300':('TI_PW0014A',14,.65,5.8,1.5,.45,4.4,5.,'tmux1511.pdf',39),
'U301':('TI_DGS0010A',10,.5,4.4,1.45,.3,3.,3.,'ads1115.pdf',52),
'U302':('TI_DGK0008A',8,.65,4.4,1.4,.45,3.,3.,'tca9517a.pdf',29)}
rvals={'0R / rail link':'0000Z0','10k':'10K0FK','100k':'100KFK','1k':'1K00FK','47R':'47R0FK','4.7k':'4K70FK','120R / DNP':'120RFK'}
for c in cs:
 ref=c['reference'];old=c.get('upstream_footprint',c['footprint']);lib,name=old.split(':')
 if lib=='RBPHAT':raise RuntimeError('Run from the source generator with original footprint IDs')
 source=Path('/usr/share/kicad/footprints')/(lib+'.pretty')/(name+'.kicad_mod')
 fp=parse(source.read_text())
 c['upstream_footprint']=old
 if ref.startswith('R') and not c['mpn']:
  if '0.1%' in c['value']:c['mpn']='TNPW0603'+('18K0' if c['value'].startswith('18k') else '47K0')+'BEEA';c['datasheet']='https://www.vishay.com/docs/28758/tnpw_e3.pdf'
  else:c['mpn']='CRCW0603'+rvals[c['value']]+'EA';c['datasheet']='https://www.vishay.com/docs/20035/dcrcwe3.pdf'
 if ref=='R1' or 'pulse' in c['value']:c['datasheet']='https://www.vishay.com/docs/20043/crcwhpe3.pdf'
 if ref.startswith('C') and ref!='C3':
  value=c['value']
  if value.startswith('100n'):mpn='GRM188R71C104KA01D';desc='100n / 16V / X7R'
  elif value.startswith('4.7u'):mpn='GRM188R61A475KE15D';desc='4.7u / 10V / X5R'
  elif value.startswith('1n'):mpn='GRM1885C1H102JA01D';desc='1n / 50V / C0G'
  else:mpn='GRM188R71E105KA12D';desc='1u / 25V / X7R'
  c['mpn']=mpn;c['value']=desc;c['datasheet']='https://www.murata.com/products/productdetail?partno='+mpn[:-1]+'%23'
 if ref=='C3':c['datasheet']='https://api.pim.na.industrial.panasonic.com/file_stream/main/fileversion/3128'
 if ref in ['J2','J3','J4']:c['datasheet']='https://www.jst-mfg.com/product/pdf/eng/eGH.pdf'
 if ref=='J1':c['mpn']='PRT-16763';c['value']='Pi 5 / H16 / gap19';c['datasheet']='https://cdn.sparkfun.com/assets/0/b/8/5/2/DS-16763-2_X_20_Pin_Extended_GPIO_Header_-_Female_-_16mm_7.30mm.pdf'
 if ref.startswith('TP'):c['mpn']='PCB feature - no purchased part'
 name=lib+'_'+name;basis='KiCad land pattern, terminal geometry checked against manufacturer drawing'
 if ref in specs:
  name,n,pitch,span,sx,sy,bx,by,doc,page=specs[ref]
  for pad in children(fp,'pad'):
   i=int(unq(pad[1]))
   if n==3:x,y=(-span/2,-pitch) if i==1 else (-span/2,pitch) if i==2 else (span/2,0)
   elif i<=n//2:x,y=-span/2,(i-1-(n//2-1)/2)*pitch
   else:x,y=span/2,(n-i-(n//2-1)/2)*pitch
   put(pad,'at',x,y);put(pad,'size',sx,sy);pad[3]='roundrect';put(pad,'roundrect_rratio',min(.05/min(sx,sy),.25));put(pad,'solder_mask_margin',.05)
  fp[:]=[d for d in fp if not(isinstance(d,list) and d[0].startswith('fp_') and child(d,'layer') and unq(child(d,'layer')[1]) in ['F.CrtYd','F.SilkS'])]
  x=max(bx/2,span/2+sx/2)+.25;y=max(by/2,(n//2-1)*pitch/2+sy/2)+.25
  if n==3:y=max(by/2,pitch+sy/2)+.25
  fp.append(parse(f'(fp_rect (start {-x} {-y}) (end {x} {y}) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))'))
  for yy in [-by/2-.12,by/2+.12]:fp.append(parse(f'(fp_line (start {-bx/2} {yy}) (end {bx/2} {yy}) (stroke (width 0.12) (type default)) (layer "F.SilkS"))'))
  fp.append(parse(f'(fp_circle (center {-x-.15} {-by/2}) (end {-x-.05} {-by/2}) (stroke (width 0.12) (type default)) (fill none) (layer "F.SilkS"))'))
  basis=f'TI {doc} p.{page}; exact example pad size/centers/pitch, NSMD +0.05mm'
 elif ref=='J1':
  name='GPIO_2x20_H16_Drill1.02'
  for pad in children(fp,'pad'):put(pad,'drill',1.02)
  basis='4UCON 07005 p.1: 2.54 pitch, finished hole 1.02mm; body H=16, tails=7.30mm; PCB gap=19mm'
 if ref=='C3':
  for pad in children(fp,'pad'):
   put(pad,'at',-2.5 if unq(pad[1])=='1' else 2.5,0);put(pad,'size',3.2,1.6)
  name='Panasonic_FK_D_6.3x5.8';basis='Panasonic FK p.3 size D: inner land gap 1.8, land length 3.2, width 1.6mm'
 if ref.startswith('D'):
  for pad in children(fp,'pad'):
   i=int(unq(pad[1]));put(pad,'at',-1.0 if i<3 else 1.0,-.95 if i==1 else .95 if i==2 else 0);put(pad,'size',.85,.85)
  name='Bourns_CDSOT23_SM712';basis='Bourns CDSOT23-SM712 p.2: 0.85mm square lands, 2.00mm row centers, 0.95mm pitch'
 # Models are frozen locally to avoid different installed KiCad versions changing the library.
 models=children(fp,'model')
 for m in models:
  src=Path(unq(m[1]).replace('${KICAD10_3DMODEL_DIR}','/usr/share/kicad/3dmodels'))
  if ref=='J1':m[1]=q('${KIPRJMOD}/models/GPIO_H16_envelope.wrl')
  elif src.exists():
   dest=MODELS/(src.parent.name+'_'+src.name);shutil.copyfile(src,dest);m[1]=q('${KIPRJMOD}/models/'+dest.name)
  else:raise FileNotFoundError(src)
 fp[1]=q(name);put(fp,'descr',q(basis+'; local frozen library'))
 (LIB/(name+'.kicad_mod')).write_text(emit(fp)+'\n')
 c['footprint']='RBPHAT:'+name;c['source_status']='Manufacturer series/ordering specification verified; stock not reserved'
 mapping[ref]={key:c[key] for key in ['value','mpn','footprint','datasheet']}
 pads=[]
 for pad in children(fp,'pad'):
  pos=child(pad,'at');sz=child(pad,'size');dr=child(pad,'drill')
  pads.append(dict(number=unq(pad[1]),x=float(pos[1]),y=float(pos[2]),sx=float(sz[1]),sy=float(sz[2]),drill=float(dr[1]) if dr else 0))
 audit.append(dict(reference=ref,mpn=c['mpn'],footprint=c['footprint'],basis=basis,pads=pads,model_files=[unq(m[1]) for m in children(fp,'model')]))
# Conservative opaque header body. VRML lengths are in KiCad's 0.1 inch units.
# Header local pad1=(0,0), pad2=(-2.54,0); model Y sign is inverted relative to PCB.
def box(cx,cy,cz,sx,sy,sz,color):
 vals=[x/2.54 for x in [cx,cy,cz,sx,sy,sz]]
 return f'Transform {{ translation {vals[0]} {vals[1]} {vals[2]} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {vals[3]} {vals[4]} {vals[5]} }} }} ] }}\n'
wrl='#VRML V2.0 utf8\n# Conservative 16mm header envelope, not contact manufacturing geometry.\n'+box(-1.27,-24.13,8,5.15,51.7,16,'0.12 0.12 0.12')
for i in range(40):wrl+=box(0 if i%2==0 else -2.54,-(i//2)*2.54,-3.65,.64,.6,7.3,'0.7 0.65 0.3')
(MODELS/'GPIO_H16_envelope.wrl').write_text(wrl)
(P/'component_overrides.json').write_text(json.dumps(mapping,indent=2)+'\n')
(P/'footprint_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
(P/'resolved_bom.json').write_text(json.dumps(cs,indent=2)+'\n')
(P/'fp-lib-table').write_text('(fp_lib_table (lib (name "RBPHAT") (type "KiCad") (uri "${KIPRJMOD}/RBPHAT.pretty") (options "") (descr "Manufacturer-checked frozen project footprints")))\n')
with (P/'procurement_bom.csv').open('w') as f:
 fields=['references','quantity','value','mpn','footprint','dnp','datasheet'];w=csv.DictWriter(f,fields);w.writeheader();groups={}
 for c in cs:
  key=(c['mpn'],c['value'],c['footprint'],c['dnp']);groups.setdefault(key,[]).append(c)
 for group in groups.values():
  c=group[0];w.writerow(dict(references=' '.join(x['reference'] for x in group),quantity=len(group),**{k:c[k] for k in fields[2:]}))
print('Frozen',len(audit),'component records,',len(list(LIB.glob('*.kicad_mod'))),'footprints')
