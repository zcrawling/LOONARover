"""Read every stored message; compare acquisition journals with bag contents."""
import argparse
from collections import Counter, defaultdict
import json
import hashlib
from pathlib import Path
import struct

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from .journal import Reader
from .recorder import REQUIRED, RAW_TOF, save_json


def verify(session):
    counts, errors = Counter(), []
    stamps = defaultdict(set)
    journal_counts = Counter()
    manual = 0
    mcu_samples = defaultdict(set)
    current_samples = defaultdict(set)
    session_meta = json.loads((session/'session.json').read_text()) if (session/'session.json').exists() else {}
    stored_payloads = {}
    stored_images = {}
    stored_calibration = {}
    cls = {}
    first_bag, last_bag = {}, {}
    source_errors = []
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag'), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    types = {row.name: row.type for row in reader.get_all_topics_and_types()}
    last, gaps = {}, defaultdict(float)
    for topic, kind in types.items():
        try:
            cls[topic] = get_message(kind)
        except (ImportError, AttributeError) as error:
            errors.append(f'{topic}: unavailable message type: {error}')
    while reader.has_next():
        topic, raw, stamp = reader.read_next()
        counts[topic] += 1
        first_bag[topic] = min(first_bag.get(topic,stamp),stamp)
        last_bag[topic] = max(last_bag.get(topic,stamp),stamp)
        if topic not in cls:
            continue
        try:
            msg = deserialize_message(raw, cls[topic])
            if topic == '/rosout' and msg.level >= 40:
                source_errors.append(dict(stamp_ns=stamp,name=msg.name,message=msg.msg))
            if hasattr(msg, 'header'):
                ts = msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
                if topic in RAW_TOF or topic in ('/camera/image_raw/compressed', '/loonar/tof/depth', '/loonar/tof/amplitude', '/loonar/tof/camera_info'):
                    if ts in stamps[topic]:
                        errors.append(f'{topic}: duplicate timestamp {ts}')
                    stamps[topic].add(ts)
                if topic in last:
                    gaps[topic] = max(gaps[topic], (ts-last[topic])/1e9)
                last[topic] = ts
                if types[topic] == 'sensor_msgs/msg/Image' and len(msg.data) != msg.step*msg.height:
                    errors.append(f'{topic}: invalid image buffer size')
                if topic in RAW_TOF[:2] or topic == '/camera/image_raw/compressed':
                    stored_images[(topic, ts)] = hashlib.sha256(bytes(msg.data)).hexdigest()
                if topic == RAW_TOF[2]:
                    stored_calibration[ts] = (msg.width, msg.height, tuple(msg.k), tuple(msg.d))
                if types[topic] == 'sensor_msgs/msg/CompressedImage':
                    import cv2
                    import numpy as np
                    if cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR) is None:
                        errors.append(f'{topic}: undecodable JPEG')
            if topic.startswith('/recording/') or topic == '/camera/timing':
                event = json.loads(msg.data)
                if 'journal' in event and topic not in ('/recording/motor/feedback', '/recording/imu/sample'):
                    journal_counts[event['journal']] += 1
                    if 'payload_hex' in event:
                        stored_payloads[(event['journal'],event['seq'])] = hashlib.sha256(bytes.fromhex(event['payload_hex'])).hexdigest()
                if topic == '/recording/groundlink/frame' and event['direction'] == 'gcs_to_rover' and event['kind'] in (1, 2, 3, 4, 5):
                    manual += 1
                if topic == '/recording/mcu/rx' and event['kind'] in (32, 33):
                    mcu_samples[(event['boot'],event['session'])].add(event['sequence'])
                    offset = event.get('clock_offset_ns')
                    if offset is not None:
                        sampled = event['mcu_stamp_us']*1000+offset
                        if session_meta.get('start_ns',0) <= sampled <= event['stamp_ns']+20_000_000:
                            current_samples[(event['boot'],event['session'])].add(event['sequence'])
                if topic == '/recording/mcu/rx' and event.get('parser_errors', 0):
                    errors.append('MCU parser reported corrupt frames')
                if topic == '/recording/mcu/tx' and not event['complete']:
                    errors.append('partial MCU serial write')
        except Exception as error:
            errors.append(f'{topic}: {error}')
    source_counts = Counter()
    partial = {}
    for path in sorted((session/'raw').glob('*.journal')):
        journal = Reader(path)
        try:
            while (record := journal.read()) is not None:
                meta, data = record
                source_counts[path.name] += 1
                if meta['source'] == 'tof':
                    _, w, h, seq, stamp, *cal = struct.unpack('<4IQ12d',data[:120])
                    for topic, pixels in zip(RAW_TOF[:2], (data[120:120+w*h*2],data[120+w*h*2:])):
                        if stored_images.get((topic,stamp)) != hashlib.sha256(pixels).hexdigest():
                            errors.append(f'{topic}: source/MCAP pixel mismatch')
                    fx,fy,cx,cy,*dist=cal
                    expected=(w,h,(fx,0.,cx,0.,fy,cy,0.,0.,1.),tuple(dist))
                    if stored_calibration.get(stamp) != expected:
                        errors.append('raw CameraInfo source/MCAP mismatch')
                elif meta['source'] == 'camera':
                    key=('/camera/image_raw/compressed',meta['timing']['stamp_ns'])
                    if stored_images.get(key) != hashlib.sha256(data).hexdigest():
                        errors.append('camera source/MCAP JPEG mismatch')
                elif stored_payloads.get((path.name,meta['seq'])) != hashlib.sha256(data).hexdigest():
                    errors.append(f'{path.name}: source/MCAP binary payload mismatch')
            if journal.remaining:
                partial[path.name] = journal.remaining
        finally:
            journal.close()
    if dict(source_counts) != dict(journal_counts):
        errors.append('journal record counts do not match MCAP event counts')
    if partial:
        errors.append('incomplete source journal records')
    for path in (session/'raw').glob('*.transport.json'):
        transport=json.loads(path.read_text())
        if not transport.get('closed'):
            errors.append(f'{path.name}: producer final status missing')
        if transport.get('dropped') or transport.get('attempted') != transport.get('received'):
            errors.append(f'{path.name}: asynchronous control journal lost records')
    for topic in RAW_TOF[1:]:
        if stamps[RAW_TOF[0]] != stamps[topic]:
            errors.append(f'raw ToF pairing mismatch: {topic}')
    processed_pair = all(stamps['/loonar/tof/depth'] == stamps[t] for t in
                         ('/loonar/tof/amplitude', '/loonar/tof/camera_info'))
    if not processed_pair:
        errors.append('processed ToF depth/amplitude/info pairing mismatch')
    status_path = session/'live_status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    if dict(counts) != status.get('counts'):
        errors.append('writer counts do not match readback counts')
    if any(status.get('dds_lost', {}).values()):
        errors.append('DDS reported message loss')
    if status.get('discovery_errors'):
        errors.append('some ROS topic types could not be recorded')
    if session_meta.get('forced_termination'):
        errors.append('a capture process required forced termination')
    if any(code not in (0,130,-2) for code in session_meta.get('exit_codes',{}).values()):
        errors.append('a capture process exited with an error')
    missing = [name for name in REQUIRED if not counts[name]]
    coverage_end = session_meta.get('capture_stopped_ns',session_meta.get('end_ns'))
    ended_early = {name:round((coverage_end-last_bag[name])/1e9,3)
                  for name in REQUIRED if name != '/tf_static' and name in last_bag
                  and coverage_end is not None and coverage_end-last_bag[name]>3_000_000_000}
    report = dict(readback_complete=True, storage_integrity_ok=not errors,
        required_streams_present=not missing, missing=missing,
        errors=sorted(set(errors)), topic_counts=dict(counts),
        source_journal_counts=dict(source_counts), bag_journal_counts=dict(journal_counts),
        partial_journals=partial, maximum_header_gap_s=dict(gaps),
        stream_ended_before_capture_end_s=ended_early,
        producer_errors=source_errors,
        coverage_end_source='capture_stopped_ns' if 'capture_stopped_ns' in session_meta else 'shutdown_end_ns_fallback',
        manual_command_count=manual, manual_input_observed=manual > 0,
        mcu_sequence_gaps_all_received={f'boot={boot},session={session_id}':sum(b-a-1 for a,b in zip(sorted(seq),sorted(seq)[1:]))
                           for (boot,session_id),seq in mcu_samples.items()},
        mcu_sequence_gaps_in_capture_window={f'boot={boot},session={session_id}':sum(b-a-1 for a,b in zip(sorted(seq),sorted(seq)[1:]))
                           for (boot,session_id),seq in current_samples.items()},
        raw_tof_frames=counts[RAW_TOF[0]], processed_tof_frames=counts['/loonar/tof/depth'],
        note='Raw ToF/camera and command journals are compared exactly. ROS-only streams are checked for DDS loss, gaps and pairing; this cannot prove absence of loss before a producer emits data. No optical exposure synchronization is claimed.')
    report['ready_for_analysis'] = report['storage_integrity_ok'] and report['required_streams_present']
    report['recording_complete'] = (report['ready_for_analysis'] and not ended_early
        and not any(report['mcu_sequence_gaps_in_capture_window'].values()))
    save_json(session/'verification.json', report)
    print(json.dumps({k:report[k] for k in ('ready_for_analysis','recording_complete','missing','errors','stream_ended_before_capture_end_s','manual_command_count','raw_tof_frames','processed_tof_frames')}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session', type=Path)
    args = parser.parse_args()
    result = verify(args.session)
    raise SystemExit(0 if result['ready_for_analysis'] else 2)
