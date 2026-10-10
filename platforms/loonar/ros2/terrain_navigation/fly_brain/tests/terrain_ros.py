"""Calibrated depth + amplitude + gravity + TF through the actual terrain node."""
import json
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import Image, CameraInfo, Imu, JointState
from geometry_msgs.msg import Vector3Stamped, TransformStamped
from std_msgs.msg import String
from tf2_ros import StaticTransformBroadcaster
from loonar_terrain_core.ros import SENSOR
from loonar_fly.terrain_node import Terrain
from loonar_fly.avoidance import Avoidance


def main():
    rclpy.init()
    terrain, node = Terrain(), Node('fly_terrain_fixture')
    executor = SingleThreadedExecutor()
    executor.add_node(terrain); executor.add_node(node)
    depth_pub = node.create_publisher(Image, '/loonar/tof/depth', SENSOR)
    amp_pub = node.create_publisher(Image, '/loonar/tof/amplitude', SENSOR)
    info_pub = node.create_publisher(CameraInfo, '/loonar/tof/camera_info', SENSOR)
    gravity_pub = node.create_publisher(Vector3Stamped, '/imu/gravity', SENSOR)
    gyro_pub = node.create_publisher(Imu, '/imu/data', SENSOR)
    wheels_pub = node.create_publisher(JointState, '/wheel_states', SENSOR)
    received = []
    node.create_subscription(String, '/loonar/fly/terrain', lambda m: received.append(json.loads(m.data)), SENSOR)
    tf = StaticTransformBroadcaster(node)
    transform = TransformStamped()
    transform.header.frame_id = 'base_link'; transform.child_frame_id = 'fixture_optical'
    transform.transform.translation.x = .03575
    transform.transform.translation.z = -.0075
    q = transform.transform.rotation
    q.x, q.y, q.z, q.w = -.5, .5, -.5, .5
    tf.sendTransform(transform)
    height, width = 240, 320
    yy, xx = np.mgrid[:height, :width]
    fx, fy, cx, cy = 240., 240., 159.5, 119.5
    ground = np.full((height, width), np.nan, np.float32)
    downward = yy > cy
    ground[downward] = .0905*fy/(yy[downward]-cy)
    info = CameraInfo(height=height, width=width)
    info.header.frame_id = 'fixture_optical'
    info.k = [fx, 0., cx, 0., fy, cy, 0., 0., 1.]
    observations = {}
    try:
        for label in ('floor', 'moving_floor', 'tilted_floor', 'wall', 'low_step', 'large_step', 'pit', 'missing', 'bad_amplitude'):
            received.clear()
            depth = ground.copy()
            pitch = .10 if label == 'tilted_floor' else 0.
            if pitch:
                cp, sp = np.cos(pitch), np.sin(pitch)
                level_ray_z = -sp-cp*(yy-cy)/fy
                origin_z = -sp*.03575-cp*.0075
                depth = ((-.098-origin_z)/level_ray_z).astype(np.float32)
                depth[depth <= 0] = np.nan
            if label == 'wall':
                depth = np.minimum(np.nan_to_num(depth, nan=2.), .36).astype(np.float32)
            elif label in ('low_step', 'large_step', 'pit'):
                relief = dict(low_step=.02, large_step=.065, pit=-.08)[label]
                surface_depth = np.full_like(depth, np.nan)
                surface_depth[downward] = (.0905-relief)*fy/(yy[downward]-cy)
                beyond = ground+.03575 >= .38
                depth[beyond] = surface_depth[beyond]
                if relief > 0:
                    # Rays meeting the vertical riser before its top surface.
                    riser = beyond & (surface_depth+.03575 < .38)
                    depth[riser] = .38-.03575
            elif label == 'missing':
                depth[depth+.03575 > .32] = np.nan
            amplitude = np.full_like(depth, 100. if label != 'bad_amplitude' else 0.)
            until, next_pub = time.monotonic()+1.5, 0
            while time.monotonic() < until:
                if time.monotonic() >= next_pub:
                    stamp = node.get_clock().now().to_msg()
                    info.header.stamp = stamp; info_pub.publish(info)
                    gravity = Vector3Stamped()
                    gravity.header.stamp = stamp; gravity.header.frame_id = 'base_link'
                    gravity.vector.x = -np.sin(pitch)*9.81
                    gravity.vector.z = np.cos(pitch)*9.81; gravity_pub.publish(gravity)
                    gyro = Imu()
                    gyro.header.stamp = stamp; gyro.header.frame_id = 'base_link'
                    gyro.angular_velocity.z = .2 if label == 'moving_floor' else 0.
                    gyro_pub.publish(gyro)
                    wheels = JointState(name=['left_wheel', 'right_wheel'], position=[0., 0.],
                                        velocity=[1., 1.] if label == 'moving_floor' else [0., 0.])
                    wheels.header.stamp = stamp; wheels_pub.publish(wheels)
                    for pub, array in ((depth_pub, depth), (amp_pub, amplitude)):
                        image = Image(height=height, width=width, step=width*4, encoding='32FC1')
                        image.header.stamp = stamp; image.header.frame_id = 'fixture_optical'
                        image.data = array.tobytes(); pub.publish(image)
                    next_pub = time.monotonic()+.07
                executor.spin_once(timeout_sec=.005)
            assert received, f'no terrain for {label}'
            scene = received[-1]
            if label == 'bad_amplitude':
                assert not scene['ready']
                observations[label] = scene
                continue
            assert scene['ready'], (label, scene)
            ray = scene['directions'][3]
            decision = Avoidance().update(scene, time.monotonic(), label)
            observations[label] = dict(ray=ray, decision=decision, points=scene['point_count'],
                                       floor=scene['floor'], temporal=scene['temporal'], vision=scene['vision'],
                                       compute_ms=scene['compute_ms'])
            expected = dict(floor='none', moving_floor='none', tilted_floor='none', wall='wall', low_step='none', large_step='step_up', pit='drop', missing='none')[label]
            assert ray['obstacle'] == expected, (label, observations[label])
            if label in ('floor', 'tilted_floor', 'moving_floor'):
                assert decision['mode'] == 'cruise', observations[label]
                assert scene['floor']['measured']
                assert scene['vision']['left'] == scene['vision']['right'] == 0
            if label == 'moving_floor':
                assert scene['temporal']['frames'] == 1
            else:
                assert scene['temporal']['frames'] >= 3, observations[label]
            if label in ('wall', 'large_step'):
                assert decision['mode'] == 'turn', observations[label]
            if label == 'missing':
                assert decision['mode'] == 'cruise' and ray['unknown_ground'], observations[label]
        report = dict(passed=True, hardware=False, observations=observations)
        (Path(__file__).resolve().parents[1]/'log/terrain-ros.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report))
    finally:
        executor.shutdown(); terrain.destroy_node(); node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
