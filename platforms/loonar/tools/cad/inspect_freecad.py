import FreeCAD as App
import Import
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
p=str(root/'261004rover.step')
d=App.newDocument('rover_check')
Import.insert(p,d.Name)
rows=[]
for o in d.Objects:
 if hasattr(o,'Shape') and not o.Shape.isNull():
  b=o.Shape.BoundBox
  rows.append(dict(name=o.Name,label=o.Label,bounds_mm=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],placement=str(o.Placement)))
json.dump(rows,open(root/'hardware/tf/freecad_geometry.json','w'),ensure_ascii=False,indent=2)
print('CAD_GEOMETRY_DONE',len(rows))
