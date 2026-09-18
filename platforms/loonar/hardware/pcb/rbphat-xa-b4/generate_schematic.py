#!/usr/bin/env python3
"""Fresh, deterministic native KiCad schematic. Pin maps transcribed from cited PDFs.
No electrical data are imported from the previous rbphat design.
"""
import csv, json, uuid
from pathlib import Path
P=Path(__file__).resolve().parent
U=lambda s:str(uuid.uuid5(uuid.NAMESPACE_URL,'loonar/rbphat-rebuild/'+s))
Q=lambda s:json.dumps(str(s),ensure_ascii=False)
F=lambda size=1.27:f'(effects (font (size {size} {size})))'
OVERRIDES=json.loads((P/'component_overrides.json').read_text()) if (P/'component_overrides.json').exists() else {}
ROOT=U('root'); libs={}; bom=[]; pages=[]
# pin tuple: number, name, electrical type, side. Local y is assigned top-down.
def library(name,pins,fp='',width=20.32):
    sides={s:[p for p in pins if p[3]==s] for s in ['L','R']}
    n=max(map(len,sides.values())); height=max(10.16,(n+1)*5.08)
    if name in ['XA6','THVD1451']:height=(max(len(ps) for ps in sides.values())+1)*10.16
    geom={}; ss=[]
    for side,ps in sides.items():
        for i,(num,label,typ,_) in enumerate(ps):
            pitch=10.16 if name=='XA6' or (name=='THVD1451' and side=='R') else 5.08
            y=(len(ps)-1)*pitch/2-i*pitch; x=(-1 if side=='L' else 1)*(width/2+5.08)
            geom[str(num)]=(x,-y,side)
            ss.append(f'(pin {typ} line (at {x} {y} {0 if side=="L" else 180}) (length 5.08) (name {Q(label)} {F()}) (number {Q(num)} {F(1.0)}))')
    body=f'(symbol {Q(name)} (pin_names (offset 0.8)) (in_bom yes) (on_board yes) (property "Reference" "U" (at 0 {height/2+2.54} 0) {F()}) (property "Value" {Q(name)} (at 0 {-height/2-2.54} 0) {F()}) (property "Footprint" {Q(fp)} (at 0 0 0) (effects (font (size 1.27 1.27)) hide)) (symbol {Q(name+"_0_1")} (rectangle (start {-width/2} {height/2}) (end {width/2} {-height/2}) (stroke (width 0.254) (type default)) (fill (type background)))) (symbol {Q(name+"_1_1")} {" ".join(ss)}))'
    libs[name]=(body,geom,height,fp)
L='L'; R='R'; I='input'; O='output'; W='power_in'; B='bidirectional'; X='passive'
library('THVD1451',[(1,'VCC',W,L),(3,'D',I,L),(2,'R',O,L),(4,'GND',W,L),(5,'Y / TX+',O,R),(6,'Z / TX-',O,R),(8,'A / RX+',I,R),(7,'B / RX-',I,R)],'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',25.4)
library('LVC2G17',[(5,'VCC',W,L),(1,'1A',I,L),(3,'2A',I,L),(2,'GND',W,L),(6,'1Y',O,R),(4,'2Y',O,R)],'Package_TO_SOT_SMD:SOT-23-6')
library('LM66100',[(1,'VIN',W,L),(2,'GND',W,L),(3,'CE',I,R),(6,'VOUT','power_out',R),(5,'ST','open_collector',R),(4,'NC','no_connect',R)],'Package_TO_SOT_SMD:SOT-363_SC-70-6')
library('TLV803E',[(3,'VDD',W,L),(1,'GND',W,L),(2,'~{RESET}','open_collector',R)],'Package_TO_SOT_SMD:SOT-23')
library('TMUX1511',[(14,'VDD',W,L),(1,'SEL1',I,L),(2,'S1',X,L),(4,'SEL2',I,L),(10,'SEL3',I,L),(13,'SEL4',I,L),(7,'GND',W,L),(3,'D1',X,R),(5,'S2',X,R),(6,'D2',X,R),(9,'S3',X,R),(8,'D3',X,R),(12,'S4',X,R),(11,'D4',X,R)],'Package_SO:TSSOP-14_4.4x5mm_P0.65mm')
library('ADS1115',[(8,'VDD',W,L),(4,'AIN0',I,L),(5,'AIN1',I,L),(6,'AIN2',I,L),(7,'AIN3',I,L),(3,'GND',W,L),(10,'SCL',I,R),(9,'SDA',B,R),(1,'ADDR',I,R),(2,'ALERT/RDY','open_collector',R)],'Package_SO:MSOP-10_3x3mm_P0.5mm')
library('TCA9517A',[(1,'VCCA',W,L),(2,'SCLA',B,L),(3,'SDAA',B,L),(4,'GND',W,L),(8,'VCCB',W,R),(7,'SCLB',B,R),(6,'SDAB',B,R),(5,'EN',I,R)],'Package_SO:VSSOP-8_3x3mm_P0.65mm')
library('SM712',[(1,'LINE1',X,L),(2,'LINE2',X,L),(3,'GND',X,R)],'Package_TO_SOT_SMD:SOT-23')
library('XA6',[(i,n,X,L) for i,n in enumerate(['TX+','TX-','RX+','RX-','GND','SHIELD'],1)],'Connector_JST:JST_GH_BM05B-GHS-TBT_1x05-1MP_P1.25mm_Vertical',15.24)
library('BAT2',[(1,'BAT+',X,L),(2,'GND',X,L)],'Connector_JST:JST_GH_BM02B-GHS-TBT_1x02-1MP_P1.25mm_Vertical',15.24)
library('PI40',[(i,str(i),X,L if i%2 else R) for i in range(1,41)],'Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical',15.24)
library('TP',[(1,'TP',X,L)],'TestPoint:TestPoint_Pad_D1.5mm',5.08)
library('R',[(1,'~',X,L),(2,'~',X,R)],'Resistor_SMD:R_0603_1608Metric',5.08)
library('C',[(1,'~',X,L),(2,'~',X,R)],'Capacitor_SMD:C_0603_1608Metric',5.08)
library('CP',[(1,'+',X,L),(2,'-',X,R)],'Capacitor_SMD:CP_Elec_6.3x5.8',5.08)
library('PWR_FLAG',[(1,'PWR','power_out',L)],'',5.08)
# Conventional resistor/capacitor graphics; terminal locations remain unchanged.
for k in ['R','C','CP','PWR_FLAG','TP']:
 body,geom,h,fp=libs[k]
 start=body.index('(symbol '+Q(k+'_0_1'))
 end=body.index('(symbol '+Q(k+'_1_1'))
 if k=='R':
  graphic='(rectangle (start -2.54 1.016) (end 2.54 -1.016) (stroke (width 0.254) (type default)) (fill (type none)))'
 elif k in ['C','CP']:
  graphic=''.join(f'(polyline (pts (xy {x} -2.54) (xy {x} 2.54)) (stroke (width 0.254) (type default)) (fill (type none)))' for x in [-0.635,0.635])
  body=body.replace('(length 5.08)','(length 6.985)')
  if k=='CP':graphic+='(text "+" (at -2.54 3.81 0) (effects (font (size 1.27 1.27))))'
 elif k=='TP':
  graphic='(circle (center 0 0) (radius 2.54) (stroke (width 0.254) (type default)) (fill (type none)))'
 else:
  graphic='(polyline (pts (xy -2.54 0) (xy 0 2.54) (xy 2.54 0) (xy 0 -2.54) (xy -2.54 0)) (stroke (width 0.254) (type default)) (fill (type none)))'
 # recompute offsets after pin-length string replacements
 start=body.index('(symbol '+Q(k+'_0_1'));end=body.index('(symbol '+Q(k+'_1_1'))
 body=body[:start]+f'(symbol {Q(k+"_0_1")} {graphic}) '+body[end:]
 libs[k]=(body,geom,5.08,fp)
class Sheet:
 def __init__(self,name,title,num):
    self.name=name;self.id=ROOT if num==1 else U(name);self.num=num;self.title=title;self.items=[];self.used=set();self.terminals={};pages.append(self)
 def note(self,x,y,s,size=1.5):
    self.items.append(f'(text {Q(s)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {U(self.name+"text"+str(len(self.items)))}))')
 def comp(self,ref,kind,value,x,y,nets,mpn='',dnp=False,fp=None,source=''):
    x=round(x/1.27)*1.27;y=round(y/1.27)*1.27
    self.used.add(kind);body,geom,h,defaultfp=libs[kind];fp=defaultfp if fp is None else fp
    def prop(k,v,yy,hide=False):return f'(property {Q(k)} {Q(v)} (at {x} {yy} 0) (effects (font (size 1.27 1.27)){" hide" if hide else ""}))'
    o=OVERRIDES.get(ref,{})
    value=o.get('value',value);mpn=o.get('mpn',mpn);fp=o.get('footprint',fp);source=o.get('datasheet',source)
    path='/'+ROOT+('' if self.num==1 else '/'+self.id)
    props=prop('Reference',ref,y-h/2-4)+prop('Value',value,y-h/2-1.7)+prop('Footprint',fp,y,True)+prop('Datasheet',source,y,True)+prop('MPN',mpn,y,True)
    self.items.append(f'(symbol (lib_id "RBPHAT:{kind}") (at {x} {y} 0) (unit 1) (in_bom {"no" if ref.startswith(("#","TP","SH")) else "yes"}) (on_board {"no" if ref.startswith("#") else "yes"}) (dnp {"yes" if dnp else "no"}) (uuid {U(ref)}) {props} (instances (project "rbphat" (path {Q(path)} (reference {Q(ref)}) (unit 1)))))')
    assert set(map(str,nets))==set(geom),(ref,nets,geom)
    for number,net in nets.items():
        dx,dy,side=geom[str(number)];px=round(x+dx,4);py=round(y+dy,4)
        self.terminals[(ref,str(number))]=(px,py,net)
        if net is None:self.items.append(f'(no_connect (at {px} {py}) (uuid {U(ref+str(number)+"NC")}))');continue
        ex=px+(-7.62 if side==L else 7.62)
        self.items.append(f'(wire (pts (xy {px} {py}) (xy {ex} {py})) (stroke (width 0) (type default)) (uuid {U(ref+str(number)+"wire")}))')
        shared=net in {'CHASSIS','GND','POWER_GOOD','PI_SDA','PI_SCL','CTRL_TX','CTRL_RX','PAY_TX','PAY_RX'} or net.startswith('+3V3')
        if shared:
            self.items.append(f'(global_label {Q(net)} (shape bidirectional) (at {ex} {py} {180 if side==L else 0}) (effects (font (size 1.27 1.27)) (justify {"right" if side==L else "left"})) (uuid {U(ref+str(number)+"label")}))')
        else:
            self.items.append(f'(label {Q(net)} (at {ex} {py} 0) (effects (font (size 1.27 1.27)) (justify {"right" if side==L else "left"} bottom)) (uuid {U(ref+str(number)+"label")}))')
    if not ref.startswith('#'):bom.append(dict(reference=ref,value=value,mpn=mpn,footprint=fp,dnp=dnp,sheet=self.name,datasheet=source,pins={str(k):v for k,v in nets.items()}))
 def link(self,a,b,via=None):
    # Actual wires replace endpoint labels. Keep net names on other members.
    a=(a[0],str(a[1]));b=(b[0],str(b[1]));pa=self.terminals[a];pb=self.terminals[b]
    assert pa[2]==pb[2],(a,b,pa,pb)
    for ref,pin in [a,b]:
      ids=[U(ref+pin+'wire'),U(ref+pin+'label')]
      self.items=[i for i in self.items if not any(j in i for j in ids)]
    pts=[pa[:2]]+(via or [])+[pb[:2]]
    # A plain wire label preserves the intended net name after global labels disappear.
    self.items.append(f'(label {Q(pa[2])} (at {pa[0]} {pa[1]} 0) (effects (font (size 1.0 1.0)) (justify left bottom)) (uuid {U(str(a)+str(b)+"netname")}))')
    for i,(p,q) in enumerate(zip(pts,pts[1:])):
      assert p[0]==q[0] or p[1]==q[1],(p,q)
      self.items.append(f'(wire (pts (xy {p[0]} {p[1]}) (xy {q[0]} {q[1]})) (stroke (width 0) (type default)) (uuid {U(str(a)+str(b)+str(i))}))')
 def save(self):
    symbols='\n'.join(libs[k][0].replace('(symbol '+Q(k)+' ','(symbol '+Q('RBPHAT:'+k)+' ',1) for k in sorted(self.used))
    content=f'(kicad_sch (version 20250114) (generator "rbphat_rebuild") (uuid {self.id}) (paper "A3") (title_block (title {Q(self.title)}) (date "2026-09-11") (rev "B4") (company "LOONAR") (comment 1 "H16 socket / gap19 / Active Cooler; common ground; prototype / B4 XA horizontal")) (lib_symbols {symbols}) '+ '\n'.join(self.items)
    if self.num==1:
      for i,p in enumerate(pages[1:]):
       x=65+i*110;y=230
       content+=f'(sheet (at {x} {y}) (size 76.2 20.32) (stroke (width 0.1524) (type default)) (fill (color 0 0 0 0)) (uuid {p.id}) (property "Sheetname" {Q(p.title)} (at {x} {y-1.27} 0) (effects (font (size 1.27 1.27)) (justify left bottom))) (property "Sheetfile" "{p.name}.kicad_sch" (at {x} {y+21.59} 0) (effects (font (size 1.27 1.27)) (justify left top))) (instances (project "rbphat" (path "/{ROOT}" (page "{p.num}")))))'
      content+='(sheet_instances (path "/" (page "1")))'
    (P/(self.name+'.kicad_sch')).write_text(content+')\n')
def ti(part):return 'https://www.ti.com/lit/ds/symlink/'+part+'.pdf'
def resistor(s,ref,val,x,y,a,b,dnp=False,mpn=''):
 s.comp(ref,'R',val,x,y,{1:a,2:b},mpn,dnp)
def cap(s,ref,val,x,y,rail,polar=False):s.comp(ref,'CP' if polar else 'C',val,x,y,{1:rail,2:'GND'},'EEEFK1C101P' if polar else '')
s=Sheet('rbphat','Pi 5 interface and protected power',1)
s.note(20,20,'RBPHAT / REV B4 XA    Dual full-duplex UART + 3S battery monitor',2.5)
pins={i:None for i in range(1,41)}
for i in [1,17]:pins[i]='+3V3_PI'
for i in [6,9,14,20,25,30,34,39]:pins[i]='GND'
pins.update({3:'PI_SDA',5:'PI_SCL',7:'CTRL_TX',29:'CTRL_RX',32:'PAY_TX',33:'PAY_RX'})
s.comp('J1','PI40','Pi 5 / 16 mm socket',60,98,pins,'SparkFun PRT-16763')
s.note(20,161,'5 V and ID EEPROM pins unused.\nUART2: GPIO4/5; UART4: GPIO12/13.\nHeader body 16 mm; PCB gap 19 mm; Active Cooler below.')
s.comp('U1','LM66100','LM66100DCKR',170,55,{1:'+3V3_PI',2:'GND',3:'+3V3_RS',4:None,5:'RS_STATUS_UNUSED',6:'+3V3_RS'},'LM66100DCKR',source=ti('lm66100'))
s.comp('U2','LM66100','LM66100DCKR',285,55,{1:'ANA_FEED',2:'GND',3:'+3V3_ANA',4:None,5:'ANA_STATUS_UNUSED',6:'+3V3_ANA'},'LM66100DCKR',source=ti('lm66100'))
resistor(s,'R7','10k',170,85,'RS_STATUS_UNUSED','GND')
resistor(s,'R8','10k',365,210,'ANA_STATUS_UNUSED','GND')
resistor(s,'R1','22R pulse',285,92,'+3V3_PI','ANA_FEED',mpn='CRCW060322R0FKEAHP')
cap(s,'C1','1u / 10V',160,105,'+3V3_PI');cap(s,'C2','4.7u / 10V',160,130,'+3V3_RS')
cap(s,'C3','100u / 16V / 20%',285,125,'+3V3_ANA',True)
resistor(s,'R2','10k',160,158,'+3V3_RS','GND');resistor(s,'R3','10k',285,155,'+3V3_ANA','GND')
s.comp('U3','TLV803E','TLV803ED29DBZR',170,197,{1:'GND',2:'POWER_GOOD',3:'+3V3_PI'},'TLV803ED29DBZR',source=ti('tlv803e'))
resistor(s,'R4','10k',285,183,'+3V3_PI','POWER_GOOD');resistor(s,'R5','100k',285,208,'POWER_GOOD','GND')
resistor(s,'R6','1k',60,195,'+3V3_PI','GND')
cap(s,'C4','100n / 10V',365,55,'+3V3_PI');cap(s,'C5','1u / 10V',365,95,'ANA_FEED')
s.comp('SH1','TP','CHASSIS / M3 ring terminal',365,250,{1:'CHASSIS'})
for i,net in enumerate(['+3V3_PI','GND','ANA_FEED']):s.comp('#FLG'+str(i+1),'PWR_FLAG',net,365,135+i*25,{1:net})
s.comp('TP1','TP','ANA supply',365,225,{1:'+3V3_ANA'})
s.note(20,270,'LM66100 CE = VOUT: reverse blocking. POWER_GOOD: 2.93 V supervisor, 50 ms nominal release.\nC3 maintains ADC supply during switch opening. Validate fast power collapse on prototype; see DESIGN_REV_B.md.',1.27)
for num,prefix,base in [(2,'CTRL',100),(3,'PAY',200)]:
 s=Sheet('control' if num==2 else 'payload',prefix+' full-duplex RS-422',num)
 s.note(20,20,prefix+' / fail-safe receiver / no external bias / 2 Mbit/s target',2.3)
 def n(v):return prefix+'_'+v
 s.comp('U'+str(base),'LVC2G17','SN74LVC2G17DBVR',65,67,{5:'+3V3_PI',1:n('TX'),3:n('RO'),2:'GND',6:n('TX_BUF'),4:n('RX_BUF')},'SN74LVC2G17DBVR',source=ti('sn74lvc2g17'))
 s.comp('U'+str(base+1),'THVD1451','THVD1451DR',180,67,{1:n('VCC'),3:n('DI'),2:n('RO'),4:'GND',5:n('Y'),6:n('Z'),8:n('A'),7:n('B')},'THVD1451DR',source=ti('thvd1451'))
 s.comp('J'+str(num),'XA6','BM05B-GHS-TBT',355,77.47,{1:n('TX+'),2:n('TX-'),3:n('RX+'),4:n('RX-'),5:'GND',6:'CHASSIS'},'BM05B-GHS-TBT(LF)(SN)')
 resistor(s,'R'+str(base+8),'0R / rail link',180,130,'+3V3_RS',n('VCC'))
 s.comp('TP'+str(base),'TP',n('VCC'),180,163,{1:n('VCC')})
 s.comp('#FLG'+str(base),'PWR_FLAG',n('VCC'),180,195,{1:n('VCC')})
 resistor(s,'R'+str(base),'10k',65,112,'+3V3_PI',n('TX'))
 resistor(s,'R'+str(base+1),'47R',122,64.77,n('TX_BUF'),n('DI'))
 resistor(s,'R'+str(base+2),'47R',65,174,n('RX_BUF'),n('RX'))
 for i,(a,b) in enumerate([('Y','TX+'),('Z','TX-'),('A','RX+'),('B','RX-')]):resistor(s,'R'+str(base+3+i),'10R pulse',250,52.07+i*10.16,n(a),n(b),mpn='CRCW0603010RJNEAHP')
 for i,pin in enumerate([5,6,8,7]):
  s.link(('U'+str(base+1),pin),('R'+str(base+3+i),1))
  s.link(('R'+str(base+3+i),2),('J'+str(num),i+1))
 resistor(s,'R'+str(base+7),'120R / fitted',355,122,n('RX+'),n('RX-'),False)
 for i,pair in enumerate([('TX+','TX-'),('RX+','RX-')]):s.comp('D'+str(base+i),'SM712','CDSOT23-SM712',355,155+i*45,{1:n(pair[0]),2:n(pair[1]),3:'GND'},'CDSOT23-SM712',source='https://www.bourns.com/pdfs/CDSOT23-SM712.pdf')
 s.link(('U'+str(base),6),('R'+str(base+1),1))
 s.link(('R'+str(base+1),2),('U'+str(base+1),3))
 cap(s,'C'+str(base),'100n / 10V',65,215,'+3V3_PI');cap(s,'C'+str(base+1),'100n / 10V',180,242,n('VCC'))
 s.note(20,260,'TX pair terminates at remote receiver. Local 120R fitted. Pin 6 SHIELD -> isolated CHASSIS lug SH1.\nConnector -> TVS -> 10R -> transceiver. Reference: TI THVD14xx Figure 38 / Table 7.\nCommon ground; cross TX to remote RX. No galvanic isolation. Protection rating requires board-level testing.',1.27)
s=Sheet('battery','Battery sensing and I2C isolation',4)
s.note(20,20,'3S battery / 0 ... 12.6 V / ADS1115 address 0x48 / PGA +/-4.096 V',2.3)
s.comp('J4','BAT2','Battery sense only',50,53,{1:'BAT_RAW',2:'GND'},'BM02B-GHS-TBT(LF)(SN)')
resistor(s,'R300','47k / 0.1%',45,133.35,'BAT_RAW','BAT_MID');resistor(s,'R301','47k / 0.1%',92.71,133.35,'BAT_MID','BAT_DIV');resistor(s,'R302','18k / 0.1%',140.97,133.35,'BAT_DIV','GND');cap(s,'C300','1u / 25V',50,175,'BAT_DIV')
s.comp('U300','TMUX1511','TMUX1511PWR',170,75,{14:'+3V3_ANA',1:'POWER_GOOD',2:'BAT_DIV',3:'BAT_ADC',4:'GND',10:'GND',13:'GND',7:'GND',5:None,6:None,9:None,8:None,12:None,11:None},'TMUX1511PWR',source=ti('tmux1511'))
s.comp('U301','ADS1115','ADS1115IDGSR',295,75,{8:'+3V3_ANA',4:'BAT_ADC',5:'GND',6:'GND',7:'GND',3:'GND',10:'ADC_SCL',9:'ADC_SDA',1:'GND',2:None},'ADS1115IDGSR',source=ti('ads1115'))
resistor(s,'R303','47k / 0.1%',207.01,133.35,'BAT_ADC','GND');cap(s,'C301','1n / C0G',170,173,'BAT_ADC')
s.comp('U302','TCA9517A','TCA9517ADGKR',295,158,{1:'+3V3_PI',2:'PI_SCL',3:'PI_SDA',4:'GND',8:'+3V3_ANA',7:'ADC_SCL',6:'ADC_SDA',5:'POWER_GOOD'},'TCA9517ADGKR',source=ti('tca9517a'))
s.link(('R300',2),('R301',1))
s.link(('R301',2),('R302',1))
s.link(('U300',3),('U301',4),[(226.06,59.69),(226.06,67.31)])
resistor(s,'R304','4.7k',295,207,'+3V3_ANA','ADC_SCL');resistor(s,'R305','4.7k',295,238,'+3V3_ANA','ADC_SDA')
cap(s,'C302','100n / 10V',50,210,'+3V3_ANA');cap(s,'C303','100n / 10V',50,242,'+3V3_ANA');cap(s,'C304','100n / 10V',170,207,'+3V3_PI');cap(s,'C305','100n / 10V',170,238,'+3V3_ANA')
s.comp('TP300','TP','BAT_DIV',365,140,{1:'BAT_DIV'})
s.comp('TP301','TP','BAT_ADC',365,177,{1:'BAT_ADC'})
s.comp('TP302','TP','POWER_GOOD',365,212,{1:'POWER_GOOD'})
s.comp('TP303','TP','GND',365,245,{1:'GND'})
s.note(20,263,'Nominal VBAT = ADC_V * 8.222222 (includes R303; Ron and ADC loading not included).\nADC off leakage discharges through R303. POWER_GOOD enables switch and I2C together.\nWait >= 150 ms after enable before measurement. Sense ground must not carry motor return current.',1.27)
for s in pages:s.save()
(P/'RBPHAT.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "rbphat_rebuild")\n'+'\n'.join(v[0] for v in libs.values())+')\n')
(P/'sym-lib-table').write_text('(sym_lib_table (lib (name "RBPHAT") (type "KiCad") (uri "${KIPRJMOD}/RBPHAT.kicad_sym") (options "") (descr "Datasheet-audited project symbols")))\n')
if not (P/'rbphat.kicad_pro').exists(): (P/'rbphat.kicad_pro').write_text(json.dumps({'meta':{'filename':'rbphat.kicad_pro','version':1}},indent=2)+'\n')
(P/'components.json').write_text(json.dumps(bom,indent=2)+'\n')
with (P/'bom.csv').open('w') as f:
 fields=['reference','value','mpn','footprint','dnp','sheet','datasheet'];w=csv.DictWriter(f,fields);w.writeheader();w.writerows({k:c[k] for k in fields} for c in bom)
print(f'Generated {len(pages)} sheets, {len(bom)} components')

footlibs=sorted({c['footprint'].split(':')[0] for c in bom})
(P/'fp-lib-table').write_text('(fp_lib_table\n'+'\n'.join(f'(lib (name "{lib}") (type "KiCad") (uri "${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr ""))' for lib in footlibs)+')\n')

if OVERRIDES:
 (P/'fp-lib-table').write_text('(fp_lib_table (lib (name "RBPHAT") (type "KiCad") (uri "${KIPRJMOD}/RBPHAT.pretty") (options "") (descr "Frozen project footprints")))\n')
