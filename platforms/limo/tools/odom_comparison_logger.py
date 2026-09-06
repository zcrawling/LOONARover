#!/usr/bin/env python3
"""Record an aligned, human-readable comparison of LIMO odometry sources.

The first usable samples define the zero reference.  This is intentional:
the wheel odometer node starts its integrated pose at zero, while the MCU IMU
reports an absolute, arbitrary yaw reference.  The useful comparison during a
drive is therefore their *change* in heading, not their initial headings.

This tool never publishes a command and cannot move the vehicle.
"""

import argparse
import csv
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, JointState


def yaw_from_quaternion(q) -> float:
    """Return Z yaw in radians from a ROS quaternion."""
    sin_yaw = 2.0 * (q.w * q.z + q.x * q.y)
    cos_yaw = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(sin_yaw, cos_yaw)


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass
class OdomSample:
    stamp_s: float
    x_m: float
    y_m: float
    yaw_rad: float
    linear_x_mps: float
    angular_z_rps: float
    received_monotonic: float


@dataclass
class ImuSample:
    stamp_s: float
    yaw_rad: float
    gyro_z_rps: float
    received_monotonic: float


@dataclass
class WheelSample:
    stamp_s: float
    left_m: float
    right_m: float
    received_monotonic: float


def stamp_seconds(header) -> float:
    return header.stamp.sec + header.stamp.nanosec * 1e-9


class ComparisonLogger(Node):
    def __init__(self, writer: csv.DictWriter, print_period_s: float):
        super().__init__("loonar_limo_odom_comparison_logger")
        self.writer = writer
        self.print_period_s = print_period_s
        self.last_print = 0.0
        self.started_monotonic = time.monotonic()
        self.imu: Optional[ImuSample] = None
        self.wheel: Optional[WheelSample] = None
        self.encoder: Optional[OdomSample] = None
        self.ekf: Optional[OdomSample] = None
        self.imu_zero: Optional[float] = None
        self.encoder_zero: Optional[OdomSample] = None
        self.ekf_zero: Optional[OdomSample] = None
        self.rows = 0

        # The live LIMO driver and the custom wheel odometer use BEST_EFFORT.
        # SensorDataQoS is therefore required; the default RELIABLE subscriber
        # would silently be incompatible with /wheel/odom.
        self.create_subscription(Imu, "/imu", self.on_imu, qos_profile_sensor_data)
        self.create_subscription(JointState, "/wheel/odometer", self.on_wheel,
                                 qos_profile_sensor_data)
        self.create_subscription(Odometry, "/wheel/odom", self.on_encoder,
                                 qos_profile_sensor_data)
        self.create_subscription(Odometry, "/odometry/filtered", self.on_ekf,
                                 qos_profile_sensor_data)

    def on_imu(self, msg: Imu):
        self.imu = ImuSample(stamp_seconds(msg.header), yaw_from_quaternion(msg.orientation),
                             msg.angular_velocity.z, time.monotonic())

    def on_wheel(self, msg: JointState):
        if len(msg.position) != 2:
            self.get_logger().warn("/wheel/odometer does not contain left/right positions")
            return
        self.wheel = WheelSample(stamp_seconds(msg.header), msg.position[0], msg.position[1],
                                 time.monotonic())

    @staticmethod
    def odom_sample(msg: Odometry) -> OdomSample:
        return OdomSample(stamp_seconds(msg.header), msg.pose.pose.position.x,
                          msg.pose.pose.position.y, yaw_from_quaternion(msg.pose.pose.orientation),
                          msg.twist.twist.linear.x, msg.twist.twist.angular.z, time.monotonic())

    def on_encoder(self, msg: Odometry):
        self.encoder = self.odom_sample(msg)

    def on_ekf(self, msg: Odometry):
        self.ekf = self.odom_sample(msg)
        self.write_row_if_ready()

    def write_row_if_ready(self):
        if not all((self.imu, self.wheel, self.encoder, self.ekf)):
            return
        if self.imu_zero is None:
            self.imu_zero = self.imu.yaw_rad
            self.encoder_zero = self.encoder
            self.ekf_zero = self.ekf
            self.get_logger().info("All four streams received; zero reference captured.")

        imu = self.imu
        wheel = self.wheel
        encoder = self.encoder
        ekf = self.ekf
        encoder_zero = self.encoder_zero
        ekf_zero = self.ekf_zero
        assert self.imu_zero is not None and encoder_zero is not None and ekf_zero is not None

        now = time.monotonic()
        encoder_yaw_delta = wrap(encoder.yaw_rad - encoder_zero.yaw_rad)
        imu_yaw_delta = wrap(imu.yaw_rad - self.imu_zero)
        ekf_yaw_delta = wrap(ekf.yaw_rad - ekf_zero.yaw_rad)
        row = {
            "elapsed_s": f"{now - self.started_monotonic:.6f}",
            "imu_stamp_s": f"{imu.stamp_s:.9f}",
            "wheel_stamp_s": f"{wheel.stamp_s:.9f}",
            "encoder_stamp_s": f"{encoder.stamp_s:.9f}",
            "ekf_stamp_s": f"{ekf.stamp_s:.9f}",
            "imu_age_s": f"{now - imu.received_monotonic:.6f}",
            "wheel_age_s": f"{now - wheel.received_monotonic:.6f}",
            "encoder_age_s": f"{now - encoder.received_monotonic:.6f}",
            "imu_yaw_delta_rad": f"{imu_yaw_delta:.9f}",
            "imu_gyro_z_rps": f"{imu.gyro_z_rps:.9f}",
            "wheel_left_m": f"{wheel.left_m:.9f}",
            "wheel_right_m": f"{wheel.right_m:.9f}",
            "encoder_x_m": f"{encoder.x_m:.9f}",
            "encoder_y_m": f"{encoder.y_m:.9f}",
            "encoder_delta_x_m": f"{encoder.x_m - encoder_zero.x_m:.9f}",
            "encoder_delta_y_m": f"{encoder.y_m - encoder_zero.y_m:.9f}",
            "encoder_yaw_delta_rad": f"{encoder_yaw_delta:.9f}",
            "encoder_vx_mps": f"{encoder.linear_x_mps:.9f}",
            "encoder_wz_rps": f"{encoder.angular_z_rps:.9f}",
            "ekf_x_m": f"{ekf.x_m:.9f}",
            "ekf_y_m": f"{ekf.y_m:.9f}",
            "ekf_delta_x_m": f"{ekf.x_m - ekf_zero.x_m:.9f}",
            "ekf_delta_y_m": f"{ekf.y_m - ekf_zero.y_m:.9f}",
            "ekf_yaw_delta_rad": f"{ekf_yaw_delta:.9f}",
            "ekf_vx_mps": f"{ekf.linear_x_mps:.9f}",
            "ekf_wz_rps": f"{ekf.angular_z_rps:.9f}",
            "encoder_minus_imu_yaw_rad": f"{wrap(encoder_yaw_delta - imu_yaw_delta):.9f}",
            "ekf_minus_imu_yaw_rad": f"{wrap(ekf_yaw_delta - imu_yaw_delta):.9f}",
            "ekf_minus_encoder_yaw_rad": f"{wrap(ekf_yaw_delta - encoder_yaw_delta):.9f}",
            "ekf_minus_encoder_x_m": f"{ekf.x_m - encoder.x_m:.9f}",
            "ekf_minus_encoder_y_m": f"{ekf.y_m - encoder.y_m:.9f}",
        }
        self.writer.writerow(row)
        self.rows += 1

        if now - self.last_print >= self.print_period_s:
            self.last_print = now
            print(
                "t={elapsed_s}s | yaw Δ rad: imu={imu_yaw_delta_rad}, enc={encoder_yaw_delta_rad}, "
                "ekf={ekf_yaw_delta_rad} | enc-imu={encoder_minus_imu_yaw_rad}, "
                "ekf-imu={ekf_minus_imu_yaw_rad} | displacement m: enc=({encoder_delta_x_m}, "
                "{encoder_delta_y_m}), ekf=({ekf_delta_x_m}, {ekf_delta_y_m})".format(**row),
                flush=True,
            )


FIELDS = [
    "elapsed_s", "imu_stamp_s", "wheel_stamp_s", "encoder_stamp_s", "ekf_stamp_s",
    "imu_age_s", "wheel_age_s", "encoder_age_s", "imu_yaw_delta_rad", "imu_gyro_z_rps",
    "wheel_left_m", "wheel_right_m", "encoder_x_m", "encoder_y_m", "encoder_delta_x_m",
    "encoder_delta_y_m", "encoder_yaw_delta_rad",
    "encoder_vx_mps", "encoder_wz_rps", "ekf_x_m", "ekf_y_m", "ekf_delta_x_m", "ekf_delta_y_m",
    "ekf_yaw_delta_rad",
    "ekf_vx_mps", "ekf_wz_rps", "encoder_minus_imu_yaw_rad", "ekf_minus_imu_yaw_rad",
    "ekf_minus_encoder_yaw_rad", "ekf_minus_encoder_x_m", "ekf_minus_encoder_y_m",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output CSV path (parent directory must exist).")
    parser.add_argument("--print-period", type=float, default=1.0, help="Console status period in seconds.")
    args = parser.parse_args()
    if args.print_period <= 0.0:
        parser.error("--print-period must be positive")
    output = os.path.abspath(args.output)
    if not os.path.isdir(os.path.dirname(output)):
        parser.error(f"output directory does not exist: {os.path.dirname(output)}")

    rclpy.init()
    try:
        with open(output, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            logger = ComparisonLogger(writer, args.print_period)
            print(f"Recording to {output}. Press Ctrl-C to finish.", flush=True)
            try:
                rclpy.spin(logger)
            except KeyboardInterrupt:
                pass
            finally:
                logger.destroy_node()
                print(f"Saved {logger.rows} aligned EKF samples to {output}.", flush=True)
    finally:
        # SIGINT received by rclpy.spin() can already shut down the context.
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
