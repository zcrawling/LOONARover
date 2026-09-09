"""Explicit sensor/GT contracts. Endpoint tape measurements are never window GT."""
import csv
import json
import math
from pathlib import Path

import numpy as np

from .core import AXES


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def read_run(directory):
    directory = Path(directory)
    meta = json.loads((directory/'run.json').read_text())
    for key in ('run_id', 'terrain_id', 'profile_id', 'preparation_id'):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise ValueError('Missing run metadata: ' + key)
    path = directory/'records.jsonl'
    if path.exists():
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        with (directory/'records.csv').open() as source:
            records = list(csv.DictReader(source))
        for row in records:
            for key in ('t', *AXES, 'vx', 'wz'):
                if row.get(key) not in (None, ''):
                    row[key] = float(row[key])
    last = {}
    for row in records:
        kind = row['kind']
        if kind not in ('imu', 'wheel'):
            continue
        required = ('t', *AXES) if kind == 'imu' else ('t', 'vx', 'wz')
        if not all(math.isfinite(float(row[k])) for k in required):
            raise ValueError('Nonfinite sensor sample')
        if kind in last and row['t'] <= last[kind]:
            raise ValueError('Non-increasing sensor stamps; split the run at time resets')
        last[kind] = row['t']
    if set(last) != {'imu', 'wheel'}:
        raise ValueError('Run needs both IMU and wheel samples')
    return meta, records


def ground_truth(directory, meta, max_gap):
    path = Path(directory)/'gt.csv'
    if not path.exists():
        return None
    if not meta.get('gt_source') or meta.get('gt_kind') not in ('external', 'pseudo'):
        raise ValueError('GT needs documented external/pseudo source in run.json')
    with path.open() as source:
        rows = list(csv.DictReader(source))
    a = np.asarray([[float(r['t'])+float(meta.get('gt_time_offset_s', 0)), float(r['s_m'])] for r in rows])
    if len(a) < 2 or not np.isfinite(a).all() or np.any(np.diff(a[:, 0]) <= 0):
        raise ValueError('Invalid or non-increasing external GT')
    def at(t):
        if t < a[0, 0] or t > a[-1, 0]:
            return None
        i = int(np.searchsorted(a[:, 0], t))
        if i < len(a) and abs(a[i, 0]-t) < 1e-8:
            return float(a[i, 1])
        if i == 0 or i == len(a) or a[i, 0]-a[i-1, 0] > max_gap:
            return None
        return float(np.interp(t, a[:, 0], a[:, 1]))
    def distance(start, end):
        x, y = at(start), at(end)
        if x is None or y is None:
            return None
        overlaps = (a[1:, 0] > start) & (a[:-1, 0] < end)
        if np.any(np.diff(a[:, 0])[overlaps] > max_gap):
            return None
        return y-x
    return distance


def export_bag(args):
    from rosbags.highlevel import AnyReader
    from rosbags.typesys import Stores, get_typestore
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    if args.gt_topic and (args.gt_topic in (args.wheel_topic, '/odometry/filtered', '/wheel/odom_corrected') or not args.gt_source):
        raise ValueError('GT must be an independent reference with --gt-source')
    meta = dict(run_id=args.run_id, terrain_id=args.terrain_id, preparation_id=args.preparation_id,
                profile_id=args.profile_id, gt_kind=args.gt_kind if args.gt_topic else None,
                gt_source=args.gt_source, gt_time_offset_s=0.0,
                imu_topic=args.imu_topic, wheel_topic=args.wheel_topic, source_bag=str(Path(args.bag).resolve()),
                units='accel:m/s^2 gyro:rad/s wheel_vx:m/s wheel_wz:rad/s', no_slip=args.no_slip)
    counts = {'imu': 0, 'wheel': 0, 'cmd': 0}
    poses = []
    frames = {}
    with AnyReader([Path(args.bag)], default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as reader, (out/'records.jsonl').open('w') as stream:
        topics = {args.imu_topic, args.wheel_topic, args.gt_topic, args.cmd_topic}
        for connection, received, raw in reader.messages(connections=[c for c in reader.connections if c.topic in topics]):
            m = reader.deserialize(raw, connection.msgtype)
            if connection.topic == args.cmd_topic:
                if connection.msgtype != 'geometry_msgs/msg/Twist':
                    raise ValueError('Command export currently requires unstamped Twist')
                stream.write(json.dumps(dict(kind='cmd',t=received/1e9,vx=m.linear.x,wz=m.angular.z),allow_nan=False)+'\n')
                counts['cmd'] += 1
                continue
            t = m.header.stamp.sec+m.header.stamp.nanosec/1e9
            if connection.topic == args.imu_topic:
                if connection.msgtype != 'sensor_msgs/msg/Imu':
                    raise ValueError('IMU topic must be sensor_msgs/Imu')
                if m.linear_acceleration_covariance[0] == -1 or m.angular_velocity_covariance[0] == -1:
                    raise ValueError('IMU reports acceleration/gyro unavailable')
                a, g = m.linear_acceleration, m.angular_velocity
                row = dict(kind='imu', t=t, received_t=received/1e9, ax=a.x, ay=a.y, az=a.z, gx=g.x, gy=g.y, gz=g.z)
                frame = m.header.frame_id
            elif connection.topic == args.wheel_topic:
                if connection.msgtype != 'nav_msgs/msg/Odometry':
                    raise ValueError('Wheel topic must be nav_msgs/Odometry')
                row = dict(kind='wheel', t=t, received_t=received/1e9,
                           vx=m.twist.twist.linear.x, wz=m.twist.twist.angular.z)
                frame = m.child_frame_id
            else:
                if connection.msgtype != 'nav_msgs/msg/Odometry':
                    raise ValueError('GT exporter requires external nav_msgs/Odometry of base_link')
                if m.child_frame_id != args.gt_base_frame or not m.header.frame_id:
                    raise ValueError('External GT must describe the configured robot base, not a camera/tag')
                if 'gt' in frames and frames['gt'] != m.header.frame_id:
                    raise ValueError('GT coordinate frame changed')
                frames['gt'] = m.header.frame_id
                p, q = m.pose.pose.position, m.pose.pose.orientation
                poses.append((t, np.array([p.x, p.y, p.z]), np.array([q.x, q.y, q.z, q.w])))
                continue
            if not frame or (row['kind'] in frames and frames[row['kind']] != frame):
                raise ValueError('Missing or changing sensor frame')
            frames[row['kind']] = frame
            counts[row['kind']] += 1
            stream.write(json.dumps(row, allow_nan=False)+'\n')
    if not counts['imu'] or not counts['wheel']:
        raise ValueError('Bag does not contain both requested inputs')
    meta.update(imu_frame=frames['imu'], wheel_frame=frames['wheel'], counts=counts)
    if args.gt_topic:
        if len(poses) < 2:
            raise ValueError('Requested GT not found')
        # Projection on external reference's midpoint body-forward axis. Preserves
        # reverse sign and slopes; excludes lateral travel from longitudinal label.
        distance = 0.0
        with (out/'gt.csv').open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['t', 's_m'])
            for i, (t, p, q) in enumerate(poses):
                if not np.isfinite(np.r_[t, p, q]).all() or not 0.99 < np.linalg.norm(q) < 1.01:
                    raise ValueError('Invalid GT pose/quaternion')
                if i:
                    prev_t, prev_p, prev_q = poses[i-1]
                    if t <= prev_t:
                        raise ValueError('GT timestamp reset')
                    qq = q if q @ prev_q >= 0 else -q
                    mid = qq+prev_q
                    mid /= np.linalg.norm(mid)
                    x, y, z, w = mid
                    forward = np.array([1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)])
                    distance += float((p-prev_p) @ forward)
                writer.writerow([t, distance])
        meta['gt_definition'] = 'signed longitudinal displacement of external base pose; must correct marker lever arm upstream'
    write_json(out/'run.json', meta)
    print(json.dumps(meta, indent=2))
