"""Recorded terrain through real old/new Body callbacks. No motor or DDS output.

Neural coverage is evaluated separately; this does not fabricate missing ToF frames
or claim physical travel. Earlier drive bags are inspected for command/block reasons.
"""
import json
from pathlib import Path
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch
import rclpy
from std_msgs.msg import String
from loonar_fly.body_node import Body
from loonar_fly.drive_node import Driver
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

OUT=Path(__file__).resolve().parent

def main():
    data=json.loads((OUT/'capture_20261009_140206_482217.json').read_text())
    rclpy.init()
    old=Body();new=Driver(Path('/tmp/nonexistent-offline-gateway.sock'))
    result={}
    try:
        for label,node in [('old_300ms',old),('new_1000ms',new)]:
            accepted=0;input_count=[];decisions=Counter()
            node.input_pub=SimpleNamespace(publish=lambda m:input_count.append(json.loads(m.data)))
            for scene in data['terrain']:
                wall=scene['stamp']+scene['age_at_bag_s']
                node.get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=int(wall*1e9)))
                # Remove offline analysis fields; use original recorded scene.
                payload={k:v for k,v in scene.items() if k not in ('t','age_at_bag_s','offline_decision')}
                node.depth_at=scene['stamp']
                with patch('time.monotonic',return_value=wall):
                    node.on_terrain(String(data=json.dumps(payload)))
                    if node.scene and node.scene['frame_id']==scene['frame_id']:
                        accepted+=1;decisions[node.decision['mode']]+=1
                    node.send_input()
            result[label]={'terrain_frames':len(data['terrain']),'terrain_accepted':accepted,
                           'input_requests_on_frame_arrival':len(input_count),'decisions':dict(decisions)}
        assert result['new_1000ms']['terrain_accepted']==len(data['terrain'])
        assert result['new_1000ms']['input_requests_on_frame_arrival']==len(data['terrain'])
        assert result['new_1000ms']['terrain_accepted']>result['old_300ms']['terrain_accepted']
    finally:
        old.destroy_node();new.mode.close();new.destroy_node();rclpy.shutdown()
    result['scope']='Recorded terrain replay through actual callbacks; no new neural inference, motor commands, or simulated distance. 46s ToF disappearance is not repaired by replay.'
    (OUT/'terrain_replay.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    summaries=[]
    for folder in sorted(Path('/work/loonar-bags').glob('drive_20261009*')):
        reader=rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(folder),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
        types={x.name:x.type for x in reader.get_all_topics_and_types()}
        topics=[t for t in ('/loonar/fly/status','/loonar/fly/result','/cmd_vel','/rosout') if t in types]
        reader.set_filter(rosbag2_py.StorageFilter(topics=topics))
        classes={t:get_message(types[t]) for t in topics}
        reasons=Counter();counts=Counter();v=[];errors=[]
        while reader.has_next():
            topic,raw,t=reader.read_next();m=deserialize_message(raw,classes[topic]);counts[topic]+=1
            if topic=='/loonar/fly/status':reasons[json.loads(m.data).get('blocked_reason','')]+=1
            elif topic=='/cmd_vel':v.append((m.linear.x,m.angular.z))
            elif topic=='/rosout' and m.level>=40:errors.append(m.msg)
        row={'bag':folder.name,'counts':dict(counts),'blocked_reasons':dict(reasons),
             'cmd_vel_recorded':bool(v),'nonzero_cmd_vel':sum(bool(x or y) for x,y in v) if v else None,'errors':dict(Counter(errors))}
        summaries.append(row);print(json.dumps(row),flush=True)
    (OUT/'earlier_drives.json').write_text(json.dumps(summaries,indent=2)+'\n')

if __name__=='__main__':main()
