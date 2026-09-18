#!/usr/bin/env python3
"""Timed motion and rosbag recording through a single ordered publisher."""
import argparse
import datetime
import json
import math
import os
import signal
import subprocess
import time
import sys
import threading
from pathlib import Path

import rclpy
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Imu, JointState
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
import yaml


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError('value must be finite')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linear', type=finite, required=True)
    parser.add_argument('--angular', type=finite, required=True)
    parser.add_argument('--duration', type=finite, required=True)
    parser.add_argument('--external-stop', action='store_true', help='Run until SIGINT from the integrated AprilTag distance test')
    parser.add_argument('--name', default='motion')
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error('--duration must be positive')
    if not args.name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.name):
        parser.error('--name must contain only letters, digits, _ or -')
    trial = Path.home() / 'odom_tests' / (datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f_') + args.name)
    trial.mkdir(parents=True)
    metadata = dict(name=args.name, requested_linear_mps=args.linear,
                    requested_angular_radps=args.angular, requested_duration_s=args.duration,
                    actual_distance_m=None, actual_heading_error_deg=None,
                    external_stop=args.external_stop, status='preparing', ros_domain_id=os.environ.get('ROS_DOMAIN_ID', '0'))
    def save():
        (trial / 'trial.yaml').write_text(yaml.safe_dump(metadata, sort_keys=False))
    save()
    interrupted = False
    paused = args.external_stop
    def external_commands():
        nonlocal paused, interrupted
        for line in sys.stdin:
            command = line.strip()
            if command == 'PAUSE': paused = True
            elif command == 'RESUME': paused = False
            elif command == 'STOP':
                interrupted = True
                return
        interrupted = True
    if args.external_stop:
        threading.Thread(target=external_commands,daemon=True).start()
    def interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('loonar_odom_motion_test')
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)
    bag = None
    started = None
    events = (trial / 'command-events.jsonl').open('w', buffering=1)
    wheel_samples = (trial / 'wheel-samples.csv').open('w', buffering=1)
    wheel_samples.write('t,vx,wz\n')
    def receive(msg, topic):
        received.add(topic)
        if topic == '/wheel/odom':
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
            wheel_samples.write(f'{stamp:.9f},{msg.twist.twist.linear.x},{msg.twist.twist.angular.z}\n')
    log = (trial / 'rosbag.log').open('w')
    def publish(linear, angular, kind):
        msg = Twist()
        msg.linear.x, msg.angular.z = linear, angular
        publisher.publish(msg)
        events.write(json.dumps(dict(event=kind, monotonic_s=time.monotonic(),
                                     ros_stamp_ns=node.get_clock().now().nanoseconds,
                                     linear_mps=linear, angular_radps=angular)) + '\n')
    try:
        received = set()
        subscriptions = []
        for topic, message in [('/imu',Imu),('/wheel/odometer',JointState),
                               ('/wheel/odom',Odometry),('/odometry/filtered',Odometry)]:
            subscriptions.append(node.create_subscription(message,topic,
                lambda msg, topic=topic: receive(msg,topic),qos_profile_sensor_data))
        deadline = time.monotonic()+10
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            driver = any(s.node_name=='limo_base_node' for s in node.get_subscriptions_info_by_topic('/cmd_vel'))
            if driver and len(received)==4:break
            if interrupted:return
        else:
            raise RuntimeError(f'LIMO driver/sensor inputs not ready; received={sorted(received)}, driver_subscribed={driver}. No motion started.')
        print('READY: LIMO driver, IMU, wheel encoder and EKF data received.',flush=True)
        for name in ('loonar_limo_wheel_odometer', 'ekf_filter_node'):
            with (trial / (name + '-params.yaml')).open('w') as output:
                try:
                    subprocess.run(['ros2', 'param', 'dump', '/' + name], stdout=output,
                                   stderr=subprocess.STDOUT, timeout=5, start_new_session=True)
                except subprocess.TimeoutExpired:
                    output.write('\n# Parameter snapshot timed out\n')
            if interrupted:
                break
        if interrupted:
            metadata['status'] = 'interrupted_before_motion'
            return
        topics = ['/cmd_vel', '/wheel/odometer', '/wheel/odom', '/vendor/velocity_odom',
                  '/imu', '/odometry/filtered', '/tf', '/tf_static', '/limo_status']
        bag = subprocess.Popen(['ros2', 'bag', 'record', '-o', str(trial / 'bag'), *topics],
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'Recording: {trial}', flush=True)
        deadline = time.monotonic() + 15
        while "Subscribed to topic '/cmd_vel'" not in (trial / 'rosbag.log').read_text():
            if interrupted:
                metadata['status'] = 'interrupted_before_motion'
                return
            if bag.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Recorder did not subscribe to /cmd_vel; see rosbag.log')
            time.sleep(0.05)
        publish(0.0, 0.0, 'baseline')
        baseline_end = time.monotonic() + 1
        while time.monotonic() < baseline_end and not interrupted:
            time.sleep(0.01)
        if interrupted:
            metadata['status'] = 'interrupted_before_motion'
            return
        print(f'Running: linear={args.linear} m/s angular={args.angular} rad/s duration={args.duration} s', flush=True)
        started = time.monotonic()
        deadline = float('inf') if args.external_stop else started + args.duration
        next_tick = started
        metadata['command_start_ros_ns'] = node.get_clock().now().nanoseconds
        while not interrupted and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0)
            now = time.monotonic()
            if now >= next_tick:
                publish(0.0 if paused else args.linear, 0.0 if paused else args.angular,
                        'tracking_pause' if paused else 'motion')
                next_tick = now + 0.05
            time.sleep(max(0, min(0.005, deadline - time.monotonic())))
        metadata['status'] = 'interrupted' if interrupted else 'completed'
    except Exception as error:
        metadata['status'] = 'failed'
        metadata['error'] = str(error)
        raise
    finally:
        # A single publisher means no old motion command can follow this stop.
        if started is not None:
            publish(0.0, 0.0, 'stop')
            metadata['command_stop_ros_ns'] = node.get_clock().now().nanoseconds
            metadata['actual_command_duration_s'] = time.monotonic() - started
        if bag is not None and bag.poll() is None:
            time.sleep(1)
            bag.send_signal(signal.SIGINT)
            try:
                bag.wait(timeout=15)
            except subprocess.TimeoutExpired:
                bag.terminate()
                bag.wait(timeout=5)
                metadata['bag_error'] = 'Recorder did not finalize within 15 seconds'
            metadata['bag_exit_code'] = bag.returncode
        save()
        events.close()
        wheel_samples.close()
        log.close()
        node.destroy_node()
        rclpy.shutdown()
        print(f'Saved: {trial / "trial.yaml"}\nFill actual_distance_m and actual_heading_error_deg.', flush=True)


if __name__ == '__main__':
    main()
