#!/usr/bin/env python3
"""Replay sensor-only bags in isolated ROS domain 168; compare EKF yaw inputs."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

# Set before importing ROS. No /cmd_vel is played and no base driver is launched.
os.environ['ROS_DOMAIN_ID'] = '168'
os.environ['ROS_LOCALHOST_ONLY'] = '1'
import rclpy
from nav_msgs.msg import Odometry
import yaml


def yaw(message):
    q = message.pose.pose.orientation
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


def main():
    root = Path.home() / 'loonar_ws/src/loonar/platforms/limo'
    params = yaml.safe_load((root / 'ros2/loonar_limo_localization/config/imu_velocity_ekf.yaml').read_text())['ekf_filter_node']['ros__parameters']
    rclpy.init()
    node = rclpy.create_node('ekf_replay_observer')
    results = []
    for trial in sorted((Path.home() / 'odom_tests').glob('20260905_15*')):
        if 'isolated' in trial.name or not (trial / 'bag').exists():
            continue
        samples = {'before': [], 'after': []}
        subs = [node.create_subscription(Odometry, '/' + name + '/odom',
                 lambda m, name=name: samples[name].append(m), 100) for name in samples]
        with tempfile.TemporaryDirectory(prefix='loonar-ekf-replay-') as work:
            children = []
            log = open(Path(work) / 'replay.log', 'w')
            try:
                for name in samples:
                    p = dict(params)
                    p['odom0_config'] = list(params['odom0_config'])
                    p['odom0_config'][11] = name == 'before'
                    p['use_sim_time'] = True
                    p['publish_tf'] = False
                    config = Path(work) / (name + '.yaml')
                    config.write_text(yaml.safe_dump({'/**': {'ros__parameters': p}}))
                    children.append(subprocess.Popen([
                        'ros2', 'run', 'robot_localization', 'ekf_node', '--ros-args',
                        '--params-file', str(config), '-r', '__node:=ekf_' + name,
                        '-r', 'odometry/filtered:=/' + name + '/odom'],
                        stdout=log, stderr=log, start_new_session=True))
                time.sleep(2)
                player = subprocess.Popen(['ros2', 'bag', 'play', str(trial / 'bag'),
                    '--clock', '--rate', '2', '--topics', '/wheel/odom', '/imu', '/tf_static'],
                    stdout=log, stderr=log, start_new_session=True)
                children.append(player)
                deadline = time.monotonic() + 45
                while player.poll() is None and time.monotonic() < deadline:
                    rclpy.spin_once(node, timeout_sec=0.05)
                for _ in range(10):
                    rclpy.spin_once(node, timeout_sec=0.05)
                if player.poll() is None:
                    raise RuntimeError('Replay timeout')
                result = {'trial': trial.name}
                for name, messages in samples.items():
                    if not messages:
                        raise RuntimeError('No EKF output: ' + log.name + '\n' + Path(log.name).read_text()[-3000:])
                    ys = [yaw(m) for m in messages]
                    angle = sum(math.atan2(math.sin(b-a), math.cos(b-a)) for a,b in zip(ys,ys[1:]))
                    first, last = messages[0].pose.pose.position, messages[-1].pose.pose.position
                    result[name] = dict(samples=len(messages), yaw_change_deg=math.degrees(angle),
                                        displacement_m=math.hypot(last.x-first.x,last.y-first.y),
                                        x_m=last.x-first.x, y_m=last.y-first.y)
                results.append(result)
                print(json.dumps(result), flush=True)
            finally:
                for child in children:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGINT)
                for child in children:
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGTERM)
                        child.wait(timeout=5)
                log.close()
        for sub in subs:
            node.destroy_subscription(sub)
    (Path.home() / 'odom_tests/ekf-replay-comparison.json').write_text(json.dumps(results, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
