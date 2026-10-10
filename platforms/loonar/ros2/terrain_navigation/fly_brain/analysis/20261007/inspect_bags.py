import json,sys
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
root=Path('/work/loonar-bags')
topics=['/loonar/fly/status','/loonar/fly/terrain','/loonar/fly/input','/recording/groundlink/frame','/recording/motor/feedback','/loonar/base/state','/recording/tof/frame','/recording/imu/sample']
r=rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=str(root/'capture_20261007_161712_443193/bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
types={x.name:x.type for x in r.get_all_topics_and_types()}; r.set_filter(rosbag2_py.StorageFilter(topics=topics))
seen=set()
while r.has_next():
 t,d,stamp=r.read_next()
 if t in seen: continue
 msg=deserialize_message(d,get_message(types[t])); print(t,str(msg)[:9000]); seen.add(t)
 if len(seen)==len(topics):break
