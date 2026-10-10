"""Real MCAP readback from loss-independent acquisition records; no hardware."""
from pathlib import Path
import os
import struct
import tempfile
import time
import cv2
import numpy as np
import rclpy
from sensor_msgs.msg import Imu
from rclpy.qos import qos_profile_sensor_data
from loonar_recording.journal import emit
from loonar_recording.recorder import Recorder
from loonar_recording.verify import verify

with tempfile.TemporaryDirectory() as tmp:
    session=Path(tmp)
    (session/'raw').mkdir()
    os.environ['LOONAR_CAPTURE_SESSION']=tmp
    rclpy.init()
    node=Recorder(session)
    publisher=node.create_publisher(Imu,'/imu/data',qos_profile_sensor_data)
    node.discover()
    meta=struct.pack('<4IQ12d',0x4c544f46,4,3,1,time.time_ns(),10.,10.,1.5,1.,*([0.]*8))
    emit('tof','sdk_frame',meta+np.arange(24,dtype=np.uint16).tobytes())
    ok,jpeg=cv2.imencode('.jpg',np.zeros((8,8,3),np.uint8))
    emit('camera','jpeg',jpeg.tobytes(),timing=dict(stamp_ns=time.time_ns(),published_frames=1),frame_id='camera_optical_frame')
    emit('groundlink','frame',struct.pack('<dd',.2,-.3),direction='gcs_to_rover',kind=2,ground_sequence=1)
    until=time.monotonic()+1
    while time.monotonic()<until:
        publisher.publish(Imu())
        rclpy.spin_once(node,timeout_sec=.02)
    node.finish()
    node.destroy_node()
    rclpy.shutdown()
    report=verify(session)
    assert report['storage_integrity_ok'],report
    assert report['raw_tof_frames']==1
    assert report['manual_command_count']==1
    assert report['topic_counts']['/imu/data']>0
    assert not report['ready_for_analysis']  # missing streams must not pass silently
    # Alter a source pixel without changing lengths/counts: readback must catch it.
    path=next((session/'raw').glob('tof-*.journal'))
    raw=bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
    corrupted=verify(session)
    assert not corrupted['storage_integrity_ok']
    assert any('pixel mismatch' in error for error in corrupted['errors'])
    print('ROS_MCAP_ROUNDTRIP_OK')
