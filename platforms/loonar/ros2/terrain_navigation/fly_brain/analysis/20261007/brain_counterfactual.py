"""Isolated open-loop neural probe; recorded inputs, no ROS or hardware.

Inputs are supplied at consecutive 10 ms neural ticks, NOT original wall-time
intervals. This tests neural/readout capacity, not closed-loop driving quality.
"""
from pathlib import Path
import json,time
import numpy as np
from loonar_fly.brain import WholeBrain
from loonar_fly.interface import rates_from_features,decode_candidate,WallTimeReadout
from loonar_fly.avoidance import Avoidance
P=Path(__file__).resolve().parent
packets=[]
for path in sorted(P.glob('capture_*.json')):packets.extend(json.loads(path.read_text())['input'])
print('LOADING',len(packets),'recorded packets',flush=True)
brain=WholeBrain(seed=1,motivation_hz=150)
brain.store_baseline();brain.step({},1)
output={}
for condition in ['neutral_input','recorded_input']:
 brain.reset(seed=1); rows=[];count=[0];smooth=WallTimeReadout()
 def next_input():
  i=count[0];count[0]+=1
  packet=packets[i%len(packets)]
  rates=rates_from_features(packet,150) if condition=='recorded_input' else {'LC4_left':0.,'LC4_right':0.,'LPLC2_left':0.,'LPLC2_right':0.,'DNp09_left':150.,'DNp09_right':150.}
  return packet,rates
 def result(packet,r):
  candidate=decode_candidate(smooth.update(r['population_hz'],len(rows)*.1))
  rows.append(dict(candidate=candidate,after_recorded_avoidance=Avoidance.command(candidate,packet['avoidance']),hz=r['population_hz'],compute_ms=r['compute_ms']))
 brain.stream(next_input,result,lambda:len(rows)>=80,10)
 last=rows[20:]
 output[condition]=dict(rows=rows,median_forward=float(np.median([x['candidate']['linear_mps'] for x in last])),positive_forward_fraction=float(np.mean([x['candidate']['linear_mps']>.02 for x in last])),median_abs_turn=float(np.median([abs(x['candidate']['angular_rps']) for x in last])),median_after_avoidance_forward=float(np.median([x['after_recorded_avoidance']['linear_mps'] for x in last])),compute_ms=float(np.median([x['compute_ms'] for x in last])))
 print(condition,{k:v for k,v in output[condition].items() if k!='rows'},flush=True)
output['method']='Same model/seed reset; 80 consecutive 10 ms neural windows per condition; last 60 summarized. Readout assumes 0.1 s wall ticks. Does not reproduce bag wall-time gaps or predict real-world trajectory.'
(P/'brain_counterfactual.json').write_text(json.dumps(output,indent=2))
