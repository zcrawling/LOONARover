"""ROS 2 subscriber to the backend's live sample socket; never owns the serial port."""

import json
import math
import os
from pathlib import Path
import socket
import struct
import time


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu, MagneticField
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import Vector3Stamped
    from .config import load, geometry

    class Bridge(Node):
        def __init__(self):
            super().__init__("loonar_mcu_sensors")
            defaults = {
                "registry": "/etc/loonar/mcu-registry.json",
                "socket": "/run/loonar/mcu/samples.sock",
                "imu_frame": "imu_link",
                "gyro_variance": 0.0,
                "wheel_v_variance": 0.0,
                "wheel_w_variance": 0.0,
            }
            for k, v in defaults.items():
                self.declare_parameter(k, v)
            self.device = load(self.get_parameter("registry").value, "control")
            self.geometry = geometry(self.device)
            self.gyro_var = float(self.get_parameter("gyro_variance").value)
            self.wheel_var = float(self.get_parameter("wheel_v_variance").value)
            self.yaw_var = float(self.get_parameter("wheel_w_variance").value)
            if any(
                not math.isfinite(v) or v < 0
                for v in (
                    (self.gyro_var, self.wheel_var, self.yaw_var)
                    if self.geometry
                    else (self.gyro_var,)
                )
            ):
                raise ValueError("gyro/wheel variances must be finite and nonnegative")
            self.frame = self.get_parameter("imu_frame").value
            self.imu = self.create_publisher(Imu, "/imu/data", qos_profile_sensor_data)
            self.accel = self.create_publisher(
                Imu, "/imu/accel", qos_profile_sensor_data
            )
            self.orientation = self.create_publisher(
                Imu, "/imu/orientation_raw", qos_profile_sensor_data
            )
            self.mag = self.create_publisher(
                MagneticField, "/imu/magnetic_field", qos_profile_sensor_data
            )
            self.linear = self.create_publisher(
                Vector3Stamped, "/imu/linear_acceleration", qos_profile_sensor_data
            )
            self.gravity = self.create_publisher(
                Vector3Stamped, "/imu/gravity", qos_profile_sensor_data
            )
            self.wheel = self.create_publisher(
                Odometry, "/wheel/odom", qos_profile_sensor_data
            )
            self.path = Path(self.get_parameter("socket").value)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A second bridge must not steal the first bridge's live socket.
            import fcntl

            self.lock = open(str(self.path) + ".lock", "a")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path.unlink(missing_ok=True)
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.sock.bind(str(self.path))
            os.chmod(self.path, 0o660)
            self.sock.setblocking(False)
            self.last = {}
            self.create_timer(0.002, self.receive)

        def header(self, msg, stamp, frame):
            msg.header.stamp.sec = stamp // 1_000_000_000
            msg.header.stamp.nanosec = stamp % 1_000_000_000
            msg.header.frame_id = frame

        def receive(self):
            for _ in range(128):
                try:
                    raw = self.sock.recv(2048)
                except BlockingIOError:
                    return
                try:
                    d = json.loads(raw)
                    if d["role"] != "control" or d["uid"] != self.device["uid"]:
                        continue
                    stamp = int(d["stamp_ns"])
                    if not -20_000_000 <= time.time_ns() - stamp <= 200_000_000:
                        continue
                    key = (d["boot"], d["kind"])
                    seq = int(d["seq"])
                    if seq <= self.last.get(key, 0):
                        continue
                    p = bytes.fromhex(d["payload"])
                    self.publish(d["kind"], p, stamp)
                    self.last[key] = seq
                except (ValueError, KeyError, TypeError, struct.error) as error:
                    self.get_logger().warning(f"Invalid MCU sample: {error}")

        def publish(self, kind, p, stamp):
            if kind == 32 and len(p) == 36:
                sensor, status, seq, lost = struct.unpack_from("<4B", p)
                x, y, z, qw, accuracy = struct.unpack_from("<5f", p, 12)
                if not all(math.isfinite(v) for v in (x, y, z, qw, accuracy)):
                    return
                if sensor in (1, 2, 5):
                    msg = Imu()
                    self.header(msg, stamp, self.frame)
                    msg.orientation_covariance[0] = -1.0
                    msg.angular_velocity_covariance[0] = -1.0
                    msg.linear_acceleration_covariance[0] = -1.0
                    if sensor == 2:
                        msg.angular_velocity.x = x
                        msg.angular_velocity.y = y
                        msg.angular_velocity.z = z
                        msg.angular_velocity_covariance = [
                            self.gyro_var,
                            0.0,
                            0.0,
                            0.0,
                            self.gyro_var,
                            0.0,
                            0.0,
                            0.0,
                            self.gyro_var,
                        ]
                        self.imu.publish(msg)
                    elif sensor == 1:
                        msg.linear_acceleration.x = x
                        msg.linear_acceleration.y = y
                        msg.linear_acceleration.z = z
                        msg.linear_acceleration_covariance = [
                            0.0
                        ] * 9  # Unknown; not fused by the initial EKF.
                        self.accel.publish(msg)
                    else:
                        norm = math.sqrt(x * x + y * y + z * z + qw * qw)
                        if not 0.9 < norm < 1.1:
                            return
                        msg.orientation.x = x / norm
                        msg.orientation.y = y / norm
                        msg.orientation.z = z / norm
                        msg.orientation.w = qw / norm
                        msg.orientation_covariance = [0.0] * 9
                        self.orientation.publish(
                            msg
                        )  # Raw SH-2 convention; ENU verification is mandatory before fusion.
                elif sensor == 3:
                    msg = MagneticField()
                    self.header(msg, stamp, self.frame)
                    msg.magnetic_field.x = x * 1e-6
                    msg.magnetic_field.y = y * 1e-6
                    msg.magnetic_field.z = z * 1e-6
                    self.mag.publish(msg)
                elif sensor in (4, 6):
                    msg = Vector3Stamped()
                    self.header(msg, stamp, self.frame)
                    msg.vector.x = x
                    msg.vector.y = y
                    msg.vector.z = z
                    (self.linear if sensor == 4 else self.gravity).publish(msg)
            elif kind == 33 and len(p) == 64 and self.geometry:
                valid = struct.unpack_from("<I", p)[0]
                age = struct.unpack_from("<I", p, 60)[0]
                if not valid & 2 or age >= 100:
                    return
                left, right = struct.unpack_from("<ii", p, 12)
                g = self.geometry
                scale = 2 * math.pi * g["radius_m"] / g["counts_per_rev"]
                left *= scale * g["left_sign"]
                right *= scale * g["right_sign"]
                msg = Odometry()
                self.header(msg, stamp - age * 1_000_000, "odom")
                msg.child_frame_id = "base_link"
                msg.pose.pose.orientation.w = 1.0
                for i in range(6):
                    msg.pose.covariance[i * 7] = 1e6
                    msg.twist.covariance[i * 7] = 1e6
                msg.twist.twist.linear.x = (left + right) / 2
                msg.twist.twist.angular.z = (right - left) / g["track_m"]
                msg.twist.covariance[0] = self.wheel_var
                msg.twist.covariance[35] = self.yaw_var
                self.wheel.publish(msg)

        def destroy_node(self):
            if hasattr(self, "sock"):
                self.sock.close()
                self.path.unlink(missing_ok=True)
                self.lock.close()
            super().destroy_node()

    rclpy.init()
    node = None
    try:
        node = Bridge()
        rclpy.spin(node)
    finally:
        if node:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
