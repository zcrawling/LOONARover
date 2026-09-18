"""Start the LIMO's inspected Orbbec DaBai depth pipeline.

This fixes only properties directly observed on the LIMO: DaBai, USB2,
depth 640x400 Y11 at 30 Hz, and no RGB/IR/coloured point cloud.  The vendor
driver publishes ``tof_link -> tof_depth_frame -> tof_depth_optical_frame``.

The physical ``base_link -> tof_link`` transform is deliberately disabled by
default.  Vendor simulation Xacros disagree on the camera height, so a made-up
mount transform would corrupt every later 2.5D result.  Enable it only after
the values in config/limo_tof_extrinsics.yaml have been measured on this LIMO.
"""

from pathlib import Path

import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("loonar_limo_tof"))
    vendor_launch = Path(get_package_share_directory("orbbec_camera")) / "launch" / "dabai.launch.py"
    extrinsics = yaml.safe_load((share / "config" / "limo_tof_extrinsics.yaml").read_text())

    mount_arguments = [
        DeclareLaunchArgument("publish_mount_tf", default_value="true"),
        DeclareLaunchArgument("base_frame", default_value=str(extrinsics["base_frame"])),
        DeclareLaunchArgument("tof_frame", default_value=str(extrinsics["tof_frame"])),
        DeclareLaunchArgument("mount_x_m", default_value=str(extrinsics["mount_x_m"])),
        DeclareLaunchArgument("mount_y_m", default_value=str(extrinsics["mount_y_m"])),
        DeclareLaunchArgument("mount_z_m", default_value=str(extrinsics["mount_z_m"])),
        DeclareLaunchArgument("mount_roll_rad", default_value=str(extrinsics["mount_roll_rad"])),
        DeclareLaunchArgument("mount_pitch_rad", default_value=str(extrinsics["mount_pitch_rad"])),
        DeclareLaunchArgument("mount_yaw_rad", default_value=str(extrinsics["mount_yaw_rad"])),
    ]

    return LaunchDescription(
        mount_arguments
        + [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(vendor_launch)),
                launch_arguments={
                    "camera_name": "tof",
                    "enable_color": "false",
                    "enable_ir": "false",
                    "enable_depth": "true",
                    "enable_point_cloud": "true",
                    "enable_colored_point_cloud": "false",
                    "depth_width": "640",
                    "depth_height": "400",
                    "depth_fps": "30",
                    "depth_format": "Y11",
                    "publish_tf": "true",
                    "tf_publish_rate": "10.0",
                    "enable_publish_extrinsic": "false",
                    # This firmware reports one unsupported optional property.
                    # `debug` keeps the startup evidence visible; the stream
                    # itself remains the fixed depth-only configuration.
                    "log_level": "debug",
                }.items(),
            ),
            Node(
                condition=IfCondition(LaunchConfiguration("publish_mount_tf")),
                package="tf2_ros",
                executable="static_transform_publisher",
                name="loonar_limo_tof_mount_tf",
                arguments=[
                    "--x", LaunchConfiguration("mount_x_m"),
                    "--y", LaunchConfiguration("mount_y_m"),
                    "--z", LaunchConfiguration("mount_z_m"),
                    "--roll", LaunchConfiguration("mount_roll_rad"),
                    "--pitch", LaunchConfiguration("mount_pitch_rad"),
                    "--yaw", LaunchConfiguration("mount_yaw_rad"),
                    "--frame-id", LaunchConfiguration("base_frame"),
                    "--child-frame-id", LaunchConfiguration("tof_frame"),
                ],
            ),
        ]
    )
