"""One MCAP: discovered ROS streams + loss-independent acquisition journals."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import shutil
import signal
import struct
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.event_handler import SubscriptionEventCallbacks
from rclpy.serialization import serialize_message
from rosidl_runtime_py.utilities import get_message
import rosbag2_py
from sensor_msgs.msg import Image, CameraInfo, CompressedImage
from std_msgs.msg import String

from .journal import Reader

RAW_TOF = ['/loonar/tof/raw_depth', '/loonar/tof/raw_amplitude', '/loonar/tof/raw_camera_info']
JOURNAL_TOPICS = set(RAW_TOF + ['/camera/image_raw/compressed', '/camera/timing'])
REQUIRED = RAW_TOF + ['/camera/image_raw/compressed', '/camera/timing', '/imu/data',
    '/imu/accel', '/imu/gravity', '/imu/orientation_raw', '/wheel_states',
    '/loonar/base/state', '/tf_static', '/recording/mcu/rx', '/recording/mcu/tx',
    '/recording/motor/feedback', '/recording/tof/frame']


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


class Recorder(Node):
    def __init__(self, session):
        super().__init__('loonar_complete_recorder')
        self.session = session
        self.writer = rosbag2_py.SequentialWriter()
        self.writer.open(rosbag2_py.StorageOptions(uri=str(session/'bag'), storage_id='mcap',
            max_bagfile_size=1024**3, max_cache_size=64*1024**2,
            storage_preset_profile='zstd_fast'), rosbag2_py.ConverterOptions('', ''))
        self.types, self.subs, self.readers = {}, {}, {}
        self.counts, self.lost, self.journal_counts = Counter(), Counter(), Counter()
        self.errors, self.last_receive = {}, {}
        self.journal_pending = 0
        self.create_timer(.5, self.discover)
        self.create_timer(.02, self.drain)
        self.create_timer(3., self.report)
        (session/'recorder.ready').touch()

    def register(self, topic, kind, transient=False):
        if topic in self.types:
            if self.types[topic] != kind:
                raise ValueError(f'type changed for {topic}')
            return
        qos = rosbag2_py._storage.QoS(30).reliable()
        if transient:
            qos.transient_local()
        self.writer.create_topic(rosbag2_py.TopicMetadata(id=len(self.types)+1,
            name=topic, type=kind, serialization_format='cdr', offered_qos_profiles=[qos]))
        self.types[topic] = kind

    def write(self, topic, raw, stamp=None):
        self.writer.write(topic, raw, stamp if stamp is not None else time.time_ns())
        self.counts[topic] += 1
        self.last_receive[topic] = time.monotonic()

    def message(self, topic, kind, msg, stamp):
        self.register(topic, kind)
        self.write(topic, serialize_message(msg), stamp)

    def event(self, topic, meta, stamp):
        self.message(topic, 'std_msgs/msg/String', String(data=json.dumps(meta, allow_nan=False)), stamp)

    def discover(self):
        for topic, types in self.get_topic_names_and_types():
            if topic in JOURNAL_TOPICS or topic.startswith('/recording/') or topic in self.subs:
                continue
            if len(types) != 1:
                self.errors[topic] = f'ambiguous types {types}'
                continue
            try:
                endpoints = self.get_publishers_info_by_topic(topic)
                if not endpoints:
                    continue
                cls = get_message(types[0])
                transient = all(p.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL for p in endpoints)
                reliable = all(p.qos_profile.reliability == ReliabilityPolicy.RELIABLE for p in endpoints)
                qos = QoSProfile(depth=30, reliability=ReliabilityPolicy.RELIABLE if reliable else ReliabilityPolicy.BEST_EFFORT,
                    durability=DurabilityPolicy.TRANSIENT_LOCAL if transient else DurabilityPolicy.VOLATILE)
                self.register(topic, types[0], transient)
                def loss(event, name=topic):
                    self.lost[name] += event.total_count_change
                self.subs[topic] = self.create_subscription(cls, topic,
                    lambda raw, name=topic: self.write(name, raw), qos, raw=True,
                    event_callbacks=SubscriptionEventCallbacks(message_lost=loss))
                self.errors.pop(topic, None)
            except (ImportError, AttributeError, ValueError, RuntimeError) as error:
                self.errors[topic] = str(error)

    def import_record(self, meta, data, filename):
        source, event, stamp = meta['source'], meta['event'], meta['stamp_ns']
        meta['journal'] = filename
        if source == 'tof':
            magic, w, h, seq, capture, *cal = struct.unpack('<4IQ12d', data[:120])
            if magic != 0x4c544f46 or len(data) != 120+w*h*4:
                raise ValueError('invalid journal ToF frame')
            for topic, pixels in zip(RAW_TOF[:2], (data[120:120+w*h*2], data[120+w*h*2:])):
                msg = Image(height=h, width=w, encoding='16UC1', step=w*2, data=pixels)
                msg.header.frame_id = 'tof_optical_frame'
                msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(capture, 10**9)
                self.message(topic, 'sensor_msgs/msg/Image', msg, capture)
            info = CameraInfo(height=h, width=w, distortion_model='rational_polynomial')
            info.header = msg.header
            fx, fy, cx, cy, *dist = cal
            info.k = [fx, 0., cx, 0., fy, cy, 0., 0., 1.]
            info.d = dist
            self.message(RAW_TOF[2], 'sensor_msgs/msg/CameraInfo', info, capture)
            meta.update(sdk_sequence=seq, capture_stamp_ns=capture,
                        timestamp_source='SDK_CALLBACK_PI_REALTIME', depth_scale=.001)
            self.event('/recording/tof/frame', meta, stamp)
        elif source == 'camera':
            timing = meta['timing']
            capture = timing['stamp_ns']
            msg = CompressedImage(format='jpeg', data=data)
            msg.header.frame_id = meta['frame_id']
            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(capture, 10**9)
            self.message('/camera/image_raw/compressed', 'sensor_msgs/msg/CompressedImage', msg, capture)
            self.event('/camera/timing', dict(timing, journal=filename, seq=meta['seq']), stamp)
        else:
            meta['payload_hex'] = data.hex()
            if source == 'groundlink' and event == 'frame' and meta['kind'] == 2 and len(data) == 16:
                v, w = struct.unpack('<dd', data)
                meta['manual'] = dict(linear_mps=v if math.isfinite(v) else None,
                                      angular_radps=w if math.isfinite(w) else None)
            if source == 'gateway' and len(data) == 29:
                source_id, v, w = struct.unpack_from('<Bdd', data, 12)
                meta['command'] = dict(source=source_id, linear_mps=v if math.isfinite(v) else None,
                                      angular_radps=w if math.isfinite(w) else None)
            if source == 'mcu' and event == 'tx' and meta['kind'] == 6:
                command, left, right, ttl = struct.unpack('<IiiI', bytes.fromhex(meta['payload']))
                meta['command'] = dict(command=command, left_qpps=left, right_qpps=right, ttl_ms=ttl)
            self.event(f'/recording/{source}/{event}', meta, stamp)
            if source == 'mcu' and event == 'rx' and meta['kind'] == 33:
                from mcu_v2.motor_sample import decode_motor
                try:
                    fields = dict(decoded=decode_motor(data))
                except ValueError as error:
                    fields = dict(decode_error=str(error))
                self.event('/recording/motor/feedback', dict(meta, **fields), stamp)
            if source == 'mcu' and event == 'rx' and meta['kind'] == 32:
                from mcu_v2.imu import decode_imu
                try:
                    fields = dict(decoded=decode_imu(data))
                except ValueError as error:
                    fields = dict(decode_error=str(error))
                self.event('/recording/imu/sample', dict(meta, **fields), stamp)
        self.journal_counts[filename] += 1

    def drain(self, final=False):
        for path in sorted((self.session/'raw').glob('*.journal')):
            if path.name not in self.readers:
                self.readers[path.name] = Reader(path)
        # Bounded batches keep ROS subscriptions serviced while capturing.
        for name, reader in self.readers.items():
            for _ in range(100000000 if final else 64):
                record = reader.read()
                if record is None:
                    break
                self.import_record(*record, name)
        self.journal_pending = sum(r.remaining for r in self.readers.values())

    def report(self):
        missing = [name for name in REQUIRED if not self.counts[name]]
        stale = [name for name in REQUIRED if name != '/tf_static' and self.counts[name]
                 and time.monotonic()-self.last_receive.get(name, 0) > 2]
        status = dict(stamp_ns=time.time_ns(), counts={k:v for k,v in self.counts.items() if v}, missing=missing, stale=stale,
            dds_lost=dict(self.lost), discovery_errors=self.errors,
            journal_counts=dict(self.journal_counts), journal_pending_bytes=self.journal_pending,
            free_bytes=shutil.disk_usage(self.session).free)
        save_json(self.session/'live_status.json', status)
        print(f"RECORD {sum(self.counts.values())} msgs | missing={','.join(missing) or 'none'} "
              f"stale={','.join(stale) or 'none'} | journal backlog={self.journal_pending} bytes", flush=True)

    def finish(self):
        self.drain(final=True)
        self.report()
        self.writer.close()
        for reader in self.readers.values():
            reader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('session', type=Path)
    args = parser.parse_args()
    rclpy.init(args=[])
    node = Recorder(args.session)
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        while not stopped:
            rclpy.spin_once(node, timeout_sec=.05)
    finally:
        node.finish()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
