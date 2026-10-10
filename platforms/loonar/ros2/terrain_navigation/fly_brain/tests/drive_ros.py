"""Real drive process + ROS + Unix mode protocol; synthetic sensors, no motors."""
import json
import math
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
from loonar_fly.vision import neural_features


def main(gcs=False):
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
            'heading': node.create_publisher(Imu, '/imu/orientation_raw', qos_profile_sensor_data),
            'imu': node.create_publisher(Imu, '/imu/data', qos_profile_sensor_data),
            'wheels': node.create_publisher(JointState, '/wheel_states', qos_profile_sensor_data),
            'base': node.create_publisher(BaseState, '/loonar/base/state', 1),
            'safety': node.create_publisher(SafetyState, '/loonar/safety/emergency_stop', 1),
            'result': node.create_publisher(String, '/loonar/fly/result', 1),
            'terrain': node.create_publisher(String, '/loonar/fly/terrain', qos_profile_sensor_data),
            'halt': node.create_publisher(String, '/loonar/fly/halt', 1),
        }
        state = dict(fault=False, safety=False, monitor=True, depth=True, brain=True, terrain=True, hazard='none', partial=False, unknown=False, low_step=0., neural_turn=False, surface_heading=0., age=0., worker='test-worker')
        state["heading"] = .4 if gcs else None
        lifecycle = []
        node.create_subscription(String, "/loonar/fly/lifecycle", lambda m: lifecycle.append(json.loads(m.data)), 1)
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
            if state['neural_turn']:
                rates['DNa02_left'] = 100.
            packet.update(worker_session=state['worker'], smoothed_hz=rates)
            pubs['result'].publish(String(data=json.dumps(packet)))
        node.create_subscription(String, '/loonar/fly/input', input_message, qos_profile_sensor_data)
        log = (root/('log/gcs-ros-process.log' if gcs else 'log/drive-ros-process.log')).open('w')
        process = subprocess.Popen(([sys.executable, '-m', 'loonar_fly.supervisor'] if gcs else
                                    [sys.executable, '-m', 'loonar_fly.drive_node', '--gateway-socket', path]),
                                   stdout=log, stderr=subprocess.STDOUT)

        def run(seconds):
            end, next_pub = time.monotonic() + seconds, 0
            while time.monotonic() < end:
                if time.monotonic() >= next_pub:
                    stamp = node.get_clock().now().to_msg()
                    ns = stamp.sec*10**9 + stamp.nanosec - int(state["age"]*1e9)
                    stamp.sec, stamp.nanosec = divmod(ns, 10**9)
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
                                         obstacle=hazard, support_until_m=0. if state['unknown'] else .9, unknown_ground=state['unknown'],
                                         low_step_m=state['low_step']) for h in HEADINGS])
                        scene['preferred_heading_rad'] = state['surface_heading']
                        for ray in scene['directions']:
                            ray.update(surface_confidence=1., flat_cost=.1)
                        scene['vision'] = neural_features(scene)
                        pubs['terrain'].publish(String(data=json.dumps(scene)))
                    imu = Imu(); imu.header.stamp = stamp
                    pubs['imu'].publish(imu)
                    if state['heading'] is not None:
                        imu.orientation.z=math.sin(state['heading']/2)
                        imu.orientation.w=math.cos(state['heading']/2)
                        pubs['heading'].publish(imu)
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
            if gcs:
                from gcs_ros import check
                check(run, state, auto, commands, statuses, lifecycle, modes)
                print(json.dumps(dict(passed=True, gcs_auto_stop_restart=True,
                    heading_preserved=True, readiness_wait=True, hardware=False)))
            else:
                run(3)
                assert process.poll() is None, (root/'log/drive-ros-process.log').read_text()
                assert any(v > 0 for _, v, _ in commands), 'no physical command with healthy inputs'
                assert all(0 <= v <= .2 and abs(w) <= .4 for _, v, w in commands)
                assert max(v for _, v, _ in commands) > .15, '0.2m/s setting not reached through acceleration ramp'
                for hazard in ('wall', 'step_up', 'drop'):
                    state['partial'] = True
                    state['hazard'] = hazard; run(.7)
                    assert commands[-1][1] == 0 and commands[-1][2] <= -.3, (hazard, commands[-1])
                    state['hazard'] = 'none'; run(1.5)
                    assert commands[-1][1] > 0, 'must resume once path opens'
                state.update(partial=True, unknown=True, low_step=.02, neural_turn=True)
                run(1)
                assert commands[-1][1] > .19 and commands[-1][2] == .3, commands[-1]
                state.update(partial=False, unknown=False, low_step=0., neural_turn=False)
                state['surface_heading'] = .5235987756; run(.8)
                assert commands[-1][1] > .19 and commands[-1][2] > .1, commands[-1]
                state['hazard'] = 'wall'; run(.5)
                assert commands[-1][1] == 0, 'wall avoidance must override flatness preference'
                state.update(hazard='none', surface_heading=0.); run(1)
                assert commands[-1][1] > .19
                # Recorded Oct 9 latency and sparse depth must permit full-speed drive.
                state.update(age=.5, partial=True); run(2)
                assert commands[-1][1] > .19, 'measured processing latency blocked drive'
                state['age'] = 0.
                state['worker'] = 'replacement-worker'; run(.7)
                assert commands[-1][1] > .19, 'new worker was permanently latched out'
                state['worker'] = ''; run(.7)
                assert commands[-1][1] > .19, 'missing optional worker label blocked motion'
                state['worker'] = 'test-worker'
                state['terrain'] = False; run(1.3)
                assert commands[-1][1:] == (0., 0.)
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
                state['brain'] = False; run(2)
                assert commands[-1][1:] == (0., 0.)
                state['brain'] = True; run(1)
                assert commands[-1][1] > 0
                state['depth'] = False; run(1.3)
                assert commands[-1][1] > .19, 'fresh terrain must not need duplicate depth callback'
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
                # Restart fixture, then verify a cleared motor fault resumes automatically.
                process = subprocess.Popen([sys.executable, '-m', 'loonar_fly.drive_node', '--gateway-socket', path],
                                           stdout=log, stderr=subprocess.STDOUT)
                run(5)
                assert commands[-1][1] > 0
                state['fault'] = True; run(.4)
                assert commands[-1][1:] == (0., 0.)
                state['fault'] = False; run(1)
                assert commands[-1][1] > .19
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
                              brain_loss_stop=True, fresh_terrain_without_duplicate_depth=True, terrain_loss_stop=True,
                              recorded_half_second_latency_drives=True,
                              wall_step_drop_turn=True, resumes_open_path=True, maximum_radps=.4,
                              partial_depth_can_avoid=True, unknown_low_step_neural_turn_preserve_forward=True,
                              flat_surface_steers_without_speed_cap=True, obstacle_overrides_flat_goal=True,
                              fault_auto_recovers=True, pc_halt_latched=True, maximum_mps=.2,
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
