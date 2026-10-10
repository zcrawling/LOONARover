"""Read-only Oct 9 bag analysis. Never publishes ROS messages or controls hardware."""
from pathlib import Path
from collections import Counter
import json,math,struct,sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from loonar_fly.avoidance import Avoidance
OUT=Path(__file__).resolve().parent
ROOT=Path('/work/loonar-bags')

def quant(v):
 a=np.array(v,dtype=float);a=a[np.isfinite(a)]
 return dict(n=len(a),p10=float(np.quantile(a,.1)),median=float(np.median(a)),p90=float(np.quantile(a,.9)),max=float(a.max())) if len(a) else {'n':0}

def main():
 summaries=[]
 for folder in sorted(ROOT.glob('capture_20261009*')):
  print('READ',folder.name,flush=True)
  session=json.loads((folder/'session.json').read_text()); start=session['start_ns']/1e9
  g=json.loads((folder/'configuration/control.json').read_text())['devices']['control']['geometry']
  scale=2*math.pi*g['radius_m']/g['counts_per_rev']
  r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=str(folder/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
  types={x.name:x.type for x in r.get_all_topics_and_types()}
  want=['/loonar/fly/terrain','/loonar/fly/status','/loonar/fly/input','/loonar/fly/result','/recording/groundlink/frame','/recording/gateway/rx','/recording/motor/feedback','/recording/imu/sample','/loonar/base/state','/imu/gravity','/imu/data','/wheel_states','/recording/tof/frame','/tf_static','/rosout','/loonar/tof/depth']
  r.set_filter(rosbag2_py.StorageFilter(topics=[t for t in want if t in types]));classes={t:get_message(types[t]) for t in want if t in types}
  data={k:[] for k in ['terrain','status','input','result','manual','gateway','motor','imu','gravity','gyro','base','tof','processed_age','errors','tf']}
  avoid=Avoidance();seen=set()
  while r.has_next():
   topic,raw,timestamp=r.read_next();wall=timestamp/1e9;t=wall-start
   m=deserialize_message(raw,classes[topic])
   if topic=='/loonar/tof/depth':
    data['processed_age'].append([t,wall-m.header.stamp.sec-m.header.stamp.nanosec/1e9]);continue
   if topic=='/tf_static':
    for tr in m.transforms:
     data['tf'].append(dict(parent=tr.header.frame_id,child=tr.child_frame_id,xyz=[tr.transform.translation.x,tr.transform.translation.y,tr.transform.translation.z],q=[tr.transform.rotation.x,tr.transform.rotation.y,tr.transform.rotation.z,tr.transform.rotation.w]))
   elif topic=='/rosout':
    if m.level>=40 or 'CubeEye error' in m.msg: data['errors'].append(dict(t=t,name=m.name,msg=m.msg))
   elif topic=='/loonar/base/state':data['base'].append([t,m.connected,m.motor_fault,m.auto_selected,m.reason])
   elif topic=='/imu/gravity':data['gravity'].append([m.header.stamp.sec+m.header.stamp.nanosec/1e9-start,m.vector.x,m.vector.y,m.vector.z])
   elif topic=='/imu/data':data['gyro'].append([m.header.stamp.sec+m.header.stamp.nanosec/1e9-start,m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
   elif topic=='/wheel_states':pass
   else:
    d=json.loads(m.data)
    if topic.startswith('/loonar/fly/'):
     key=topic.rsplit('/',1)[1]
     if key=='terrain':
      d['age_at_bag_s']=wall-d['stamp']
      d['offline_decision']=avoid.update(d,d['stamp'],d['frame_id'])
     data[key].append(dict(t=t,**d))
    elif topic=='/recording/tof/frame':data['tof'].append([d['capture_stamp_ns']/1e9-start,d['sdk_sequence'],(d['stamp_ns']-d['capture_stamp_ns'])/1e9])
    elif topic=='/recording/groundlink/frame':
     if d['direction']=='gcs_to_rover':
      v,w=struct.unpack('<dd',bytes.fromhex(d['payload_hex'])) if d['kind']==2 else (0.,0.)
      data['manual'].append([t,d['kind'],v,w,d['ground_sequence']])
    elif topic=='/recording/gateway/rx':
     b=bytes.fromhex(d['payload_hex'])
     if len(b)==29:
      source,v,w=struct.unpack_from('<Bdd',b,12);data['gateway'].append([t,source,v,w])
    elif topic=='/recording/motor/feedback':
     if d['clock_offset_ns'] is None:continue
     sample=d['mcu_stamp_us']/1e6+d['clock_offset_ns']/1e9; age=wall-sample
     if not -.02<=age<=.3 or sample<start:continue
     key=(d['boot'],d['session'],d['sequence'])
     if key in seen:continue
     seen.add(key);f=d.get('decoded')
     if f is None:continue
     left=f['left_speed_qpps']*scale*g['left_sign'];right=f['right_speed_qpps']*scale*g['right_sign']
     lc=f['left_command_qpps']*scale*g['left_sign'];rc=f['right_command_qpps']*scale*g['right_sign']
     data['motor'].append(dict(t=sample-start,v=(left+right)/2,w=(right-left)/g['track_m'],target_v=(lc+rc)/2,target_w=(rc-lc)/g['track_m'],age=age,**f))
    elif topic=='/recording/imu/sample':
     if d['clock_offset_ns'] is None or not d.get('decoded'):continue
     sample=d['mcu_stamp_us']/1e6+d['clock_offset_ns']/1e9
     if sample<start or not -.02<=wall-sample<=.3:continue
     dec=d['decoded']
     if dec['sensor'] in ('gyro_radps','gravity_mps2'):data['imu'].append([sample-start,dec['sensor'],*dec['values']])
  scenes=[x for x in data['terrain'] if x.get('ready')]
  center=[x['directions'][3] for x in scenes]
  motors=data['motor']; tof=np.array(data['tof']);mt=np.array(data['manual'])
  straight=[x for x in motors if abs(x['target_v'])>.05 and abs(x['target_w'])<.02]
  turning=[x for x in motors if abs(x['target_w'])>.05 and abs(x['target_v'])<.02]
  active=(float(tof[-1,0]-tof[0,0]) if len(tof)>1 else 0)
  summary=dict(session=folder.name,mode=session['mode'],duration_s=(session['end_ns']-session['start_ns'])/1e9,
   tof_frames=len(tof),tof_first_s=float(tof[0,0]) if len(tof) else None,tof_last_s=float(tof[-1,0]) if len(tof) else None,tof_active_s=active,tof_rate_hz=(len(tof)-1)/active if active else None,
   processed_frames=len(data['processed_age']),processed_age_s=quant([x[1] for x in data['processed_age']]),
   terrain_frames=len(scenes),terrain_age_s=quant([x['age_at_bag_s'] for x in scenes]),terrain_compute_ms=quant([x['compute_ms'] for x in scenes]),
   terrain_over_300ms=sum(x['age_at_bag_s']>.3 for x in scenes),floor_measured=sum(x['floor']['measured'] for x in scenes),
   floor_confidence=quant([x['floor']['confidence'] for x in scenes]),center_obstacles=dict(Counter(x['obstacle'] for x in center)),
   center_clearance=quant([x['clearance_m'] for x in center]),avoidance_modes=dict(Counter(x['offline_decision']['mode'] for x in scenes)),
   brain_inputs=len(data['input']),brain_results=len(data['result']),status_reasons=dict(Counter(x['blocked_reason'] for x in data['status'])),
   surface_selected=sum(x.get('preferred_heading_rad',0)!=0 for x in scenes),stationary_median=sum(x['temporal']['mode']=='stationary_median' for x in scenes),
   manual_counts=dict(Counter(int(x[1]) for x in data['manual'])),manual_during_tof=int(sum(tof[0,0]<=x[0]<=tof[-1,0] and x[1]==2 for x in data['manual'])) if len(tof) else 0,
   motor_samples=len(motors),motor_error_counts=dict(Counter(x['error'] for x in motors)),
   straight_speed=quant([x['v'] for x in straight]),straight_abs_tracking_error=quant([abs(x['v']-x['target_v']) for x in straight]),
   turn_speed=quant([x['w'] for x in turning]),turn_abs_tracking_error=quant([abs(x['w']-x['target_w']) for x in turning]),
   moving_samples=sum(abs(x['v'])>.02 or abs(x['w'])>.05 for x in motors),errors=data['errors'])
  (OUT/(folder.name+'.json')).write_text(json.dumps(data,separators=(',',':')))
  summaries.append(summary)
  print(json.dumps(summary),flush=True)
 (OUT/'summary.json').write_text(json.dumps(summaries,indent=2))
if __name__=='__main__':main()
