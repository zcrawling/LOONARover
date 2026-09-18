#!/usr/bin/env python3
"""Integration check in a loopback-only ROS domain, without rover subscribers."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

from rclpy.serialization import deserialize_message
from geometry_msgs.msg import Twist
import yaml


def main():
    script = Path(__file__).with_name('run_odom_motion_test.py')
    env = dict(os.environ, ROS_DOMAIN_ID='167', ROS_LOCALHOST_ONLY='1')
    results = []
    for interrupted in (False, True):
        name = 'isolated_interrupt_check' if interrupted else 'isolated_duration_check'
        process = subprocess.Popen(['python3', '-u', str(script), '--linear', '0.1',
                                    '--angular', '-0.3', '--duration', '2', '--name', name],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, start_new_session=True)
        trial = None
        for line in process.stdout:
            print(line.strip(), flush=True)
            if line.startswith('Recording: '):
                trial = Path(line.strip().split(': ', 1)[1])
            if line.startswith('Running: ') and interrupted:
                time.sleep(0.4)
                process.send_signal(signal.SIGINT)
        assert process.wait(timeout=20) == 0
        meta = yaml.safe_load((trial / 'trial.yaml').read_text())
        events = [json.loads(s) for s in (trial / 'command-events.jsonl').read_text().splitlines()]
        assert events[-1]['event'] == 'stop'
        assert meta['status'] == ('interrupted' if interrupted else 'completed')
        assert (trial / 'bag' / 'metadata.yaml').exists()
        con = sqlite3.connect(next((trial / 'bag').glob('*.db3')))
        rows = list(con.execute("select timestamp,data from messages where topic_id=(select id from topics where name='/cmd_vel') order by timestamp"))
        samples = [(t, deserialize_message(data, Twist)) for t, data in rows]
        motion = [i for i, (t, m) in enumerate(samples) if m.linear.x or m.angular.z]
        assert motion
        assert all(m.linear.x == 0.1 and m.angular.z == -0.3 for i, (t, m) in enumerate(samples) if i in motion)
        stop = motion[-1] + 1
        assert stop < len(samples), 'Final zero Twist missing from rosbag'
        assert all(m.linear.x == 0 and m.angular.z == 0 for t, m in samples[stop:])
        elapsed = (samples[stop][0] - samples[motion[0]][0]) / 1e9
        assert 0.2 < elapsed < 0.8 if interrupted else abs(elapsed - 2) < 0.1
        results.append(dict(trial=str(trial), status=meta['status'], bag_command_duration_s=elapsed,
                            motion_after_stop=False, samples=len(samples)))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
