"""Real drive process + ROS + Unix mode protocol; synthetic sensors, no motors."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, Imu, JointState
from std_msgs.msg import String
from loonar_msgs.msg import BaseState, SafetyState
from loonar_fly.avoidance import HEADINGS


def main():
    rclpy.init()
    node = Node('fly_drive_test')
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp)/'cfs.sock')
        server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        server.bind(path)
        server.listen(1)
        server.settimeout(.1)
        quit_event = threading.Event()
        modes = []
        auto = [False]

        def serve():
            while not quit_event.is_set():
                try:
                    peer, _ = server.accept()
                except socket.timeout:
                    continue
                peer.settimeout(.1)
                with peer:
                    while not quit_event.is_set():
                        try:
                            data = peer.recv(256)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        magic, version, kind, size = struct.unpack('<IHHI', data)
                        assert (magic, version, size) == (0x4c4e5247, 1, 0)
                        modes.append((time.monotonic(), kind))
                        if kind in (3, 4):
                            auto[0] = kind == 4

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        pubs = {
            'depth': node.create_publisher(Image, '/loonar/tof/depth', qos_profile_sensor_data),
            'imu': node.create_publisher(Imu, '/imu/data', qos_profile_sensor_data),
            'wheels': node.create_publisher(JointState, '/wheel_states', qos_profile_sensor_data),
            'base': node.create_publisher(BaseState, '/loonar/base/state', 1),
            'safety': node.create_publisher(SafetyState, '/loonar/safety/emergency_stop', 1),
            'result': node.create_publisher(String, '/loonar/fly/result', 1),
            'terrain': node.create_publisher(String, '/loonar/fly/terrain', qos_profile_sensor_data),
            'halt': node.create_publisher(String, '/loonar/fly/halt', 1),
        }
        state = dict(fault=False, safety=False, monitor=True, depth=True, brain=True, terrain=True, hazard='none', partial=False)
        commands = []
        statuses = []
        node.create_subscription(Twist, '/cmd_vel', lambda m: commands.append((time.monotonic(), m.linear.x, m.angular.z)), 1)
        node.create_subscription(String, '/loonar/fly/status', lambda m: statuses.append(json.loads(m.data)), 1)

        def input_message(msg):
            if not state['brain']:
                return
            packet = json.loads(msg.data)
            rates = {f'{kind}_{side}': 150. if kind == 'DNp09' else 0.
                     for kind in ('DNp09', 'DNa02') for side in ('left', 'right')}
            packet.update(worker_session='test-worker', smoothed_hz=rates)
            pubs['result'].publish(String(data=json.dumps(packet)))
        node.create_subscription(String, '/loonar/fly/input', input_message, qos_profile_sensor_data)
        log = (root/'log/drive-ros-process.log').open('w')
        process = subprocess.Popen([sys.executable, '-m', 'loonar_fly.drive_node', '--gateway-socket', path],
                                   stdout=log, stderr=subprocess.STDOUT)

        def run(seconds):
            end, next_pub = time.monotonic() + seconds, 0
            while time.monotonic() < end:
                if time.monotonic() >= next_pub:
                    stamp = node.get_clock().now().to_msg()
                    image = Image(height=8, width=8, step=32, encoding='32FC1')
                    image.header.stamp = stamp
                    values = np.ones((8, 8), np.float32)
                    if state['partial']:
                        values[:, :4] = np.nan
                    image.data = values.tobytes()
                    if state['depth']:
                        pubs['depth'].publish(image)
                    if state['terrain']:
                        hazard = state['hazard']
                        scene = dict(ready=True, stamp=stamp.sec+stamp.nanosec*1e-9,
                                     frame_id=f'{stamp.sec}:{stamp.nanosec}',
                                     turn_clear=dict(left=True, right=True),
                                     directions=[dict(heading=float(h), clearance_m=.15 if hazard != 'none' else .9,
                                         obstacle=hazard, support_until_m=.9, unknown_ground=False,
                                         low_step_m=0.) for h in HEADINGS])
                        pubs['terrain'].publish(String(data=json.dumps(scene)))
                    imu = Imu(); imu.header.stamp = stamp
                    pubs['imu'].publish(imu)
                    wheels = JointState(velocity=[0., 0.]); wheels.header.stamp = stamp
                    pubs['wheels'].publish(wheels)
                    base = BaseState(connected=True, motor_fault=state['fault'], auto_selected=auto[0], reason='test fault' if state['fault'] else 'healthy')
                    base.header.stamp = stamp
                    pubs['base'].publish(base)
                    safety = SafetyState(emergency_stop=state['safety'], reason='collision braking envelope: front gap=0.034m, required clearance=0.070m' if state['safety'] else 'clear')
                    safety.header.stamp = stamp
                    if state['monitor']:
                        pubs['safety'].publish(safety)
                    next_pub = time.monotonic() + .04
                rclpy.spin_once(node, timeout_sec=.005)
        try:
            deadline = time.monotonic() + 10
            while pubs['base'].get_subscription_count() < 1 and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.02)
            assert pubs['base'].get_subscription_count() >= 1, 'DDS discovery failed'
            run(3)
            assert process.poll() is None, (root/'log/drive-ros-process.log').read_text()
            assert any(v > 0 for _, v, _ in commands), 'no physical command with healthy inputs'
            assert all(0 <= v <= .2 and abs(w) <= .6 for _, v, w in commands)
            assert max(v for _, v, _ in commands) > .15, '0.2m/s setting not reached through acceleration ramp'
            for hazard in ('wall', 'step_up', 'drop'):
                state['partial'] = True
                state['hazard'] = hazard; run(.7)
                assert commands[-1][1] == 0 and commands[-1][2] <= -.5, (hazard, commands[-1])
                state['hazard'] = 'none'; run(1.5)
                assert commands[-1][1] > 0, 'must resume once path opens'
            state['partial'] = False
            state['terrain'] = False; run(.6)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            state['terrain'] = True; run(1)
            assert commands[-1][1] > 0
            mark = time.monotonic()
            state['safety'] = True; run(1.2)
            assert all(v > 0 for at, v, _ in commands if at >= mark)
            assert auto[0] and statuses[-1]['scene_guard_enabled'] is False
            assert '0.034m' in statuses[-1]['terrain_advisory']
            state['monitor'] = False; run(.6)
            assert commands[-1][1] > 0 and auto[0]
            state['monitor'] = True
            state['safety'] = False; run(1)
            assert commands[-1][1] > 0
            state['brain'] = False; run(1)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            state['brain'] = True; run(1)
            assert commands[-1][1] > 0
            state['depth'] = False; run(.5)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            state['depth'] = True; run(1)
            assert commands[-1][1] > 0
            # SIGINT while actually emitting nonzero commands must send mode STOP.
            start = time.monotonic()
            process.send_signal(signal.SIGINT)
            run(.4)
            stops = [at for at, kind in modes if kind == 3 and at >= start]
            assert stops and min(stops) - start < .25
            process.wait(timeout=2)
            assert process.returncode == 0
            assert not auto[0]
            sigint_ms = 1000*(min(stops)-start)
            # Restart fixture, then verify motor fault stays latched after recovery.
            process = subprocess.Popen([sys.executable, '-m', 'loonar_fly.drive_node', '--gateway-socket', path],
                                       stdout=log, stderr=subprocess.STDOUT)
            run(5)
            assert commands[-1][1] > 0
            state['fault'] = True; run(.4)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            state['fault'] = False; run(1)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            process.send_signal(signal.SIGINT); process.wait(timeout=2)
            process = subprocess.Popen([sys.executable, '-m', 'loonar_fly.drive_node', '--gateway-socket', path],
                                       stdout=log, stderr=subprocess.STDOUT)
            run(5)
            assert commands[-1][1] > 0
            pubs['halt'].publish(String(data='test-worker')); run(.4)
            assert commands[-1][1:] == (0., 0.) and not auto[0]
            run(1)
            assert commands[-1][1:] == (0., 0.)
            process.send_signal(signal.SIGINT); process.wait(timeout=2)
            report = dict(passed=True, nonzero_seen=True, bounded_speed=True,
                          proximity_advisory_does_not_stop=True, missing_scene_monitor_does_not_stop=True,
                          brain_loss_stop=True, stale_depth_stop=True, terrain_loss_stop=True,
                          wall_step_drop_turn=True, resumes_open_path=True, maximum_radps=.6,
                          partial_depth_can_avoid=True,
                          fault_latched=True, pc_halt_latched=True, maximum_mps=.2,
                          sigint_gateway_stop_ms=sigint_ms, exit_code=process.returncode,
                          hardware=False)
            (root/'log/drive-ros.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(report))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            quit_event.set(); thread.join(timeout=1); server.close(); log.close()
    node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
