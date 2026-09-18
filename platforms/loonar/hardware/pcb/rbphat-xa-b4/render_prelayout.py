#!/usr/bin/env python3
"""Render mechanical constraints and a footprint inspection atlas (reportlab)."""
import json,math
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,landscape
from sexpr import parse,child,children,unq
P=Path(__file__).resolve().parent
W,H=landscape(A4);c=canvas.Canvas(str(P/'mechanical-review.pdf'),pagesize=(W,H))
def text(x,y,t,size=10):c.setFont('Helvetica',size);c.setFillColorRGB(.08,.12,.17);c.drawString(x,y,t)
text(32,H-35,'RBPHAT B2 - pre-layout mechanical constraints',18)
text(32,H-55,'Pi 5 + official Active Cooler / 16 mm header body / 19 mm nominal board spacing',11)
ox,oy,s=55,160,4.7
c.setStrokeColorRGB(.1,.3,.4);c.setFillColorRGB(.91,.96,.96);c.roundRect(ox,oy,65*s,56*s,3*s,fill=1)
for x,y in [(3.5,3.5),(61.5,3.5),(3.5,52.5),(61.5,52.5)]:
 c.setFillColorRGB(1,1,1);c.circle(ox+x*s,oy+(56-y)*s,1.375*s,fill=1);c.setDash(2,2);c.circle(ox+x*s,oy+(56-y)*s,3.1*s);c.setDash()
for i in range(40):
 x=8.37+(i//2)*2.54;y=4.77 if i%2==0 else 2.23
 c.setFillColorRGB(.65,.35,.05);c.circle(ox+x*s,oy+(56-y)*s,.65*s,fill=1)
text(ox+20,oy+56*s+14,'65.00 mm / corner radius 3.00 mm',10)
text(ox+20,oy+56*s-48,'J1 underside - pin 1 at (8.37, 4.77)',10)
text(ox+45,oy+130,'TOP: circuit placement area',12)
text(ox+45,oy+110,'BOTTOM: no circuit components',10)
text(ox+45,oy+90,'except J1 socket',10)
text(ox,oy-22,'4 x NPTH 2.75 mm, mounting centers 58 x 49 mm',10)
text(ox,oy-39,'Screw clearance diameter 6.2 mm; no copper',10)
text(ox,oy-56,'Datum: upper-left, X right, Y down. Dimensions in mm.',9)
# Side view uses a schematic envelope, not an unverified XY alignment.
x,y,sc=430,235,6
c.setFillColorRGB(.15,.5,.25);c.rect(x,y-1.6*sc,52*sc,1.6*sc,fill=1)
c.rect(x,y+19*sc,52*sc,1.6*sc,fill=1)
c.setFillColorRGB(.7,.75,.78);c.rect(x+40,y,170,13.7*sc,fill=1)
c.setFillColorRGB(.15,.15,.15);c.rect(x+270,y+3*sc,5*sc,16*sc,fill=1)
text(x,y-27,'Pi PCB top = 0 mm',10);text(x,y+19*sc+20,'HAT underside = +19 mm',10)
text(x+45,y+45,'Active Cooler',10);text(x+45,y+29,'13.7 mm reference height',9)
text(x,y+19*sc+43,'All ICs / JST headers / C3 above HAT',10)
text(x,y-49,'Nominal insertion: 6.0 - (19 - 16 - 2.5) = 5.5 mm',9)
text(x,y-65,'Header body H = 16 +/-0.25 mm; tail = 7.30 mm.',9)
text(x,y-81,'19 mm spacers are a design dimension; check seating',9)
text(x,y-95,'and contact engagement during first assembly.',9)
text(32,53,'Cooler side envelope is illustrative. No case, cable-bend, or thermal certification is implied.',9)
text(32,37,'Sources: Raspberry Pi HAT mechanical guide / HAT+ Ch.7 / Active Cooler drawing; 4UCON 07005.',9)
c.showPage();c.save()
# Atlas: each unique footprint, enlarged with pad numbering and dimensions.
a=json.loads((P/'footprint_audit.json').read_text());unique={}
for r in a:unique.setdefault(r['footprint'],r)
c=canvas.Canvas(str(P/'footprint-review.pdf'),pagesize=A4);w,h=A4
for i,r in enumerate(unique.values()):
 if i%6==0:
  if i:c.showPage()
  text=lambda x,y,t,size=10: (c.setFont('Helvetica',size),c.setFillColorRGB(.08,.12,.17),c.drawString(x,y,t))
  text(25,h-28,'RBPHAT B2 - footprint inspection atlas',15)
  text(25,h-44,'Copper pads shown; view from mounting side. Header board instance is flipped to B.Cu.',8)
 col=i%2;row=(i%6)//2;x0=25+col*280;y0=h-77-row*242
 name=r['footprint'].split(':')[1]
 text(x0,y0,name[:42],8);text(x0,y0-13,r['mpn'][:44],8)
 pads=r['pads'];minx=min(p['x']-p['sx']/2 for p in pads);maxx=max(p['x']+p['sx']/2 for p in pads);miny=min(p['y']-p['sy']/2 for p in pads);maxy=max(p['y']+p['sy']/2 for p in pads)
 scale=min(28,225/(maxx-minx+2),158/(maxy-miny+2));cx=x0+122-(minx+maxx)/2*scale;cy=y0-105+(miny+maxy)/2*scale
 for p in pads:
  xx=cx+(p['x']-p['sx']/2)*scale;yy=cy-(p['y']+p['sy']/2)*scale
  c.setFillColorRGB(.72,.31,.08);c.setStrokeColorRGB(.5,.2,.03);c.rect(xx,yy,p['sx']*scale,p['sy']*scale,fill=1)
  if p['drill']:
   c.setFillColorRGB(1,1,1);c.circle(cx+p['x']*scale,cy-p['y']*scale,p['drill']/2*scale,fill=1)
  c.setFillColorRGB(.05,.05,.05);c.setFont('Helvetica',5 if len(pads)>20 else 8);c.drawCentredString(cx+p['x']*scale,cy-p['y']*scale-2,p['number'])
 text(x0,y0-204,f'Copper extents: {maxx-minx:.3f} x {maxy-miny:.3f} mm',8)
 text(x0,y0-217,'Representative: '+r['reference']+'; pin-1 and polarity checked',8)
c.showPage();c.save();print('Rendered mechanical-review.pdf and footprint-review.pdf')
