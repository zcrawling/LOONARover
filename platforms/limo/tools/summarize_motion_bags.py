#!/usr/bin/env python3
"""Read recorded command timing and wheel travel without publishing ROS data."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def summarize(trial):
    con = sqlite3.connect(next((trial / 'bag').glob('*.db3')))
    def read(name):
        row = con.execute('select id,type from topics where name=?', (name,)).fetchone()
        if row is None:
            return []
        cls = get_message(row[1])
        return [(t / 1e9, deserialize_message(b, cls)) for t, b in con.execute(
            'select timestamp,data from messages where topic_id=? order by timestamp', (row[0],))]
    commands = read('/cmd_vel')
    active = [i for i, (t, m) in enumerate(commands) if m.linear.x or m.angular.z]
    result = dict(trial=trial.name)
    if active:
        last_zero = next((i for i in range(active[-1]+1, len(commands))
                          if not commands[i][1].linear.x and not commands[i][1].angular.z), None)
        zeros = [i for i in range(active[0], active[-1]+1)
                 if not commands[i][1].linear.x and not commands[i][1].angular.z]
        result.update(first_motion_s=commands[active[0]][0], final_zero_recorded=last_zero is not None,
                      zeros_followed_by_motion=len(zeros),
                      first_to_last_motion_s=commands[active[-1]][0]-commands[active[0]][0],
                      first_motion_to_final_zero_s=commands[last_zero][0]-commands[active[0]][0] if last_zero else None,
                      command_linear_integral_m=sum((commands[i+1][0]-t)*m.linear.x for i, (t,m) in enumerate(commands[:-1])))
    wheels = read('/wheel/odometer')
    if wheels:
        first, last = wheels[0][1].position, wheels[-1][1].position
        result['left_travel_m'] = last[0]-first[0]
        result['right_travel_m'] = last[1]-first[1]
        result['mean_wheel_travel_m'] = (last[0]+last[1]-first[0]-first[1])/2
    for topic in ('/wheel/odom', '/odometry/filtered'):
        rows = read(topic)
        if rows:
            a, b = rows[0][1].pose.pose.position, rows[-1][1].pose.pose.position
            result[topic] = dict(endpoint_distance_m=math.hypot(b.x-a.x, b.y-a.y), samples=len(rows))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps([summarize(p) for p in sorted(args.root.iterdir())
                      if (p / 'bag').exists() and not 'isolated_' in p.name], indent=2))
