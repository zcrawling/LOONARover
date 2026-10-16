"""Payload fake MCU -> durable events -> real ROS bridge -> MCAP readback.

No USB device is opened and no actuator command is sent. Run in an isolated
ROS_DOMAIN_ID with ROS Jazzy sourced and tools/recording on PYTHONPATH.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import rclpy
import rosbag2_py
from rclpy.serialization import deserialize_message
from std_msgs.msg import String
from payload_pca_service import Service
from loonar_recording.recorder import Recorder

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root/'raw').mkdir()
    journal = root/'payload/events.jsonl'
    os.environ['LOONAR_PAYLOAD_EVENTS'] = str(journal)
    service = Service(root/'unused.sock', 'NEVER_OPEN_USB', root/'payload')
    service.send_serial = lambda command: None
    service.broadcast = lambda text: None
    def health():
        service.polls['55'] = time.monotonic()
        service.handle_line('HEALTH,1,55,0000000000000001,1,IDLE,1,100,5,0,0,payload-1')
    def done(op, error=None):
        nonce = next(k for k,v in service.pending.items() if v[1] == op)
        service.handle_line(f'ERROR,{nonce},{error}' if error else f'DONE,{nonce},{op},1')
    health(); done('RESULT', 'no_result')
    service.start(7); done('START'); service.stop(8)
    # Match the actual MLX hardware fault: the sequence still has an END event.
    pca = 'PCA,DEMO_ONLY,1,1000,6000,10,0,0,nan,nan,nan,nan,nan,nan,0,INVALID_STATION'
    service.record(pca); service.handle_line(pca); done('STOP')
    service.selector.close()
    expected = [json.loads(line) for line in journal.read_text().splitlines()]
    registry = root/'registry.json'
    registry.write_text(json.dumps({'schema':2,'devices':{'control':{'uid':'0000000000000001','device':'/dev/serial/by-id/NEVER_OPEN_USB','transport':'usb'}}}))
    log = (root/'bridge.log').open('w')
    bridge = subprocess.Popen([sys.executable, '-m', 'mcu_v2.ros_bridge', '--ros-args',
        '-p', f'registry:={registry}', '-p', f'socket:={root}/samples.sock'], stdout=log, stderr=log)
    recorder = None
    try:
        # Publish before recorder exists: transient-local history must deliver both.
        time.sleep(2)
        assert bridge.poll() is None, (root/'bridge.log').read_text()
        rclpy.init(args=[])
        recorder = Recorder(root)
        until = time.monotonic()+10
        while recorder.counts['/payload/sequence_events'] < 2 and time.monotonic()<until:
            rclpy.spin_once(recorder, timeout_sec=.1)
        assert recorder.counts['/payload/sequence_events'] == 2, (root/'bridge.log').read_text()
        recorder.finish(); recorder.destroy_node(); recorder = None
        rclpy.shutdown()
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(root/'bag'),storage_id='mcap'),
                    rosbag2_py.ConverterOptions('', ''))
        actual = []
        while reader.has_next():
            topic, raw, stamp = reader.read_next()
            if topic == '/payload/sequence_events':
                meta = json.loads(deserialize_message(raw,String).data)
                assert stamp == meta['stamp_ns']
                actual.append(meta)
        assert actual == expected, actual
        assert [x['event'] for x in actual] == ['START','END']
        assert actual[1]['result_status'] == 'INVALID_STATION'
        print('PAYLOAD_ROS_MCAP_ROUNDTRIP_OK: START/END, seq=1, exact timestamps, invalid result, late subscriber')
    finally:
        if recorder:
            recorder.finish(); recorder.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
        bridge.send_signal(signal.SIGINT)
        try: bridge.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bridge.kill(); bridge.wait()
        log.close()
