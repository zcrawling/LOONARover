"""Exclusive RGB-D camera profile for the LIMO Orbbec DaBai.

Do not run this together with loonar_limo_tof/limo_dabai_tof.launch.py: both
launches open the same USB device. This profile requests hardware depth-to-color
registration and matching 640x400 RGB/depth images for odometry.
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
    vendor_launch = Path(get_package_share_directory("orbbec_camera")) / "launch" / "dabai.launch.py"
    extrinsics_path = (
        Path(get_package_share_directory("loonar_limo_tof"))
        / "config"
        / "limo_tof_extrinsics.yaml"
    )
    with extrinsics_path.open(encoding="utf-8") as stream:
        extrinsics = yaml.safe_load(stream)

    return LaunchDescription([
        DeclareLaunchArgument(
            "publish_mount_tf",
            default_value="true",
            description="Publish the measured base_link to tof_link transform",
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="limo_tof_mount_tf",
            condition=IfCondition(LaunchConfiguration("publish_mount_tf")),
            arguments=[
                "--x", str(extrinsics["mount_x_m"]),
                "--y", str(extrinsics["mount_y_m"]),
                "--z", str(extrinsics["mount_z_m"]),
                "--roll", str(extrinsics["mount_roll_rad"]),
                "--pitch", str(extrinsics["mount_pitch_rad"]),
                "--yaw", str(extrinsics["mount_yaw_rad"]),
                "--frame-id", str(extrinsics["base_frame"]),
                "--child-frame-id", str(extrinsics["tof_frame"]),
            ],
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(vendor_launch)),
            launch_arguments={
                "camera_name": "tof",
                "enable_color": "true",
                "enable_depth": "true",
                "enable_ir": "false",
                "depth_registration": "true",
                "color_depth_synchronization": "true",
                "enable_point_cloud": "false",
                "enable_colored_point_cloud": "false",
                "color_width": "640",
                "color_height": "480",
                "color_fps": "30",
                "depth_width": "640",
                "depth_height": "400",
                "depth_fps": "30",
                "depth_format": "Y11",
                # DaBai depth is 640x400 while UVC color is 640x480. Crop color
                # to the registered depth ROI so RTAB-Map receives equal sizes.
                "color_roi_x": "0",
                "color_roi_y": "0",
                "color_roi_width": "640",
                "color_roi_height": "400",
                "depth_scale": "1",
                "publish_tf": "true",
                "tf_publish_rate": "10.0",
                "enable_publish_extrinsic": "true",
                "log_level": "info",
            }.items(),
        ),
    ])
