"""Run the physical LIMO base driver and the LOONAR encoder/IMU EKF.

This launch intentionally emits no motion command. It starts the serial driver
solely to expose MCU telemetry, keeps its legacy velocity odometry separate,
and leaves odom->base_link ownership to robot_localization.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("loonar_limo_localization"))
    port = LaunchConfiguration("port_name")

    return LaunchDescription([
        DeclareLaunchArgument("port_name", default_value="ttylimo"),
        Node(
            package="limo_base",
            executable="limo_base",
            name="limo_base_node",
            output="screen",
            parameters=[{
                "port_name": port,
                "odom_frame": "odom",
                "base_frame": "base_link",
                "pub_odom_tf": False,
                "use_mcnamu": False,
            }],
            remappings=[("odom", "/vendor/velocity_odom")],
        ),
        Node(
            package="loonar_limo_encoder_odom",
            executable="wheel_odometer_node",
            name="loonar_limo_wheel_odometer",
            output="screen",
        ),
        Node(
            package="robot_localization",
            executable="ekf_node",
            name="ekf_filter_node",
            output="screen",
            parameters=[str(share / "config" / "imu_velocity_ekf.yaml")],
        ),
    ])
