#!/usr/bin/env python3
"""Create a pre-layout board: only mechanical features and J1 fixed; other parts parked.
Run: LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu /usr/bin/python3 create_board_start.py
"""
import json,math,uuid,xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as k
P=Path(__file__).resolve().parent;mm=k.FromMM;v=lambda x,y:k.VECTOR2I(mm(x),mm(y))
b=k.BOARD();b.SetCopperLayerCount(4);ds=b.GetDesignSettings();ds.SetBoardThickness(mm(1.6))
ds.m_MinClearance=mm(.2);ds.m_CopperEdgeClearance=mm(.3);ds.m_HoleClearance=mm(.25)
root=ET.parse(P/'validation/netlist.xml').getroot();pn={};nets={}
for i,n in enumerate(root.findall('./nets/net'),1):
 name=n.attrib['name'].replace('ALERT/RDY','ALERT{slash}RDY')
 net=k.NETINFO_ITEM(b,name,i);b.Add(net);nets[name]=net
 for node in n.findall('node'):pn[(node.attrib['ref'],node.attrib['pin'])]=net
keep=[];cs=json.loads((P/'components.json').read_text());xm={c.attrib['ref']:c for c in root.findall('./components/comp')};rootid=str(uuid.uuid5(uuid.NAMESPACE_URL,'loonar/rbphat-rebuild/root'))
for i,c in enumerate(cs):
 lib,name=c['footprint'].split(':');fp=k.FootprintLoad(str(P/(lib+'.pretty')),name);assert fp
 b.Add(fp);keep.append(fp);fp.SetFPID(k.LIB_ID(lib,name));fp.SetReference(c['reference']);fp.SetValue(c['value']);fp.SetDNP(c['dnp'])
 x=xm[c['reference']];path=k.KIID_PATH();path.push_back(k.KIID(rootid))
 for id in x.find('sheetpath').attrib['tstamps'].strip('/').split('/'):
  if id:path.push_back(k.KIID(id))
 path.push_back(k.KIID(x.findtext('tstamps')));fp.SetPath(path)
 if c['reference']=='J1':
  fp.Flip(v(0,0),False);fp.SetOrientationDegrees(-90);fp.SetPosition(v(108.37,104.77));fp.SetLocked(True)
 else:fp.SetPosition(v(185+(i%6)*18,65+(i//6)*14))
 for pad in fp.Pads():
  net=pn.get((c['reference'],pad.GetNumber()))
  if net is not None:pad.SetNet(net)
# 65 x 56, 3 mm rounded corners. Datum (100,100) = HAT upper-left.
def line(a,c):
 s=k.PCB_SHAPE(b);s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(v(*a));s.SetEnd(v(*c));s.SetLayer(k.Edge_Cuts);s.SetWidth(mm(.05));b.Add(s);keep.append(s)
def arc(a,m,c):
 s=k.PCB_SHAPE(b);s.SetShape(k.SHAPE_T_ARC);s.SetArcGeometry(v(*a),v(*m),v(*c));s.SetLayer(k.Edge_Cuts);s.SetWidth(mm(.05));b.Add(s);keep.append(s)
r=3;t=3/math.sqrt(2)
line((103,100),(162,100));arc((162,100),(162+t,103-t),(165,103));line((165,103),(165,153));arc((165,153),(162+t,153+t),(162,156));line((162,156),(103,156));arc((103,156),(103-t,153+t),(100,153));line((100,153),(100,103));arc((100,103),(103-t,103-t),(103,100))
for i,(x,y) in enumerate([(103.5,103.5),(161.5,103.5),(103.5,152.5),(161.5,152.5)],1):
 fp=k.FOOTPRINT(b);fp.SetReference('H'+str(i));fp.SetValue('M2.5 / NPTH 2.75');fp.SetPosition(v(x,y));fp.SetLocked(True);b.Add(fp);keep.append(fp)
 pad=k.PAD(fp);pad.SetNumber('');pad.SetAttribute(k.PAD_ATTRIB_NPTH);pad.SetShape(k.PAD_SHAPE_CIRCLE);pad.SetSize(v(2.75,2.75));pad.SetDrillSize(v(2.75,2.75));pad.SetLayerSet(k.LSET.AllCuMask());pad.SetPosition(v(x,y));fp.Add(pad);keep.append(pad)
 s=k.PCB_SHAPE(fp);s.SetShape(k.SHAPE_T_CIRCLE);s.SetCenter(v(x,y));s.SetEnd(v(x+3.1,y));s.SetLayer(k.F_CrtYd);s.SetWidth(mm(.05));fp.Add(s);keep.append(s)
# Assert physical pin mapping after bottom-side transformation.
j=next(f for f in b.GetFootprints() if f.GetReference()=='J1');pos={p.GetNumber():(round(k.ToMM(p.GetPosition().x),2),round(k.ToMM(p.GetPosition().y),2)) for p in j.Pads()}
assert pos['1']==(108.37,104.77) and pos['2']==(108.37,102.23) and pos['39']==(156.63,104.77) and pos['40']==(156.63,102.23),pos
k.SaveBoard(str(P/'rbphat.kicad_pcb'),b)
print('Created 4-layer board, 72 linked circuit footprints + 4 mounting holes; no tracks',flush=True)
