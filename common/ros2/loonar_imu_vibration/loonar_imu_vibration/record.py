"""Read-only acquisition. The caller controls driving separately."""
import argparse
import datetime
import signal
import subprocess
from pathlib import Path

from .data import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New run directory')
    for key in ('run-id', 'terrain-id', 'preparation-id', 'profile-id'):
        parser.add_argument('--'+key, required=True)
    parser.add_argument('--imu-topic', default='/imu/data')
    parser.add_argument('--wheel-topic', default='/wheel/odom')
    parser.add_argument('--wheel-state-topic', default='/wheel/odometer')
    parser.add_argument('--gt-topic', default='/ground_truth/odom')
    parser.add_argument('--extra-topic', action='append', default=[])
    parser.add_argument('--no-slip', action='store_true')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    meta = vars(args).copy()
    meta.update(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                actual_distance_m=None, notes='', gt_source=None, status='recording',
                notice='Topics requested, not proof of their presence; inspect rosbag metadata after recording')
    write_json(out/'run.json', meta)
    topics = [args.imu_topic, args.wheel_topic, args.wheel_state_topic, args.gt_topic,
              '/cmd_vel', '/tf', '/tf_static', '/odometry/filtered', '/wheel/twist_corrected',
              '/terrain_correction/diagnostics', *args.extra_topic]
    proc = subprocess.Popen(['ros2', 'bag', 'record', '-o', str(out/'bag'), *dict.fromkeys(topics)], start_new_session=True)
    def stop(sig, frame):
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=15)
        meta.update(status='closed' if proc.returncode == 0 else 'recorder_failed', recorder_exit_code=proc.returncode)
        write_json(out/'run.json', meta)
    print(f'Saved {out}; no vehicle commands were published.')
    return code


if __name__ == '__main__':
    main()
