"""Summarize a ToF test bag using installed ROS2 readers, no robot commands."""
import sys,json
from collections import Counter
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def main():
 folder=Path(sys.argv[1]);reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(folder/'rover/bag'),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
 types={x.name:get_message(x.type) for x in reader.get_all_topics_and_types()};poses={};quality=[];clouds=0
 while reader.has_next():
  topic,raw,t=reader.read_next()
  if topic=='/tof/depth/points':clouds+=1;continue
  if topic not in ['/localization/registration','/wheel/odom','/localization/dr','/odom_tof_test']:continue
  m=deserialize_message(raw,types[topic])
  if topic=='/localization/registration':quality.append(json.loads(m.data))
  else:poses.setdefault(topic,[]).append([m.pose.pose.position.x,m.pose.pose.position.y])
 result=dict(cloud_frames=clouds,registration_attempts=quality,accepted=sum(r.get('accepted',False) for r in quality),
             displacement_m={k:float(np.linalg.norm(np.array(v[-1])-v[0])) for k,v in poses.items() if len(v)>1},
             note='Displacement is not GT accuracy. Rejected ICP preserves DR. No map TF is published in this test.')
 (folder/'icp_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(cloud_frames=clouds,accepted=result['accepted'],reasons=dict(Counter(r.get('reason','unknown') for r in quality)),displacement_m=result['displacement_m']),indent=2))
if __name__=='__main__':main()
