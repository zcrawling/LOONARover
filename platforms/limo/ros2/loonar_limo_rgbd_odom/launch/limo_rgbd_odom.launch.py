"""Run isolated RTAB-Map RGB-D odometry without publishing TF."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    rgb_topic = LaunchConfiguration("rgb_topic")
    depth_topic = LaunchConfiguration("depth_topic")
    camera_info_topic = LaunchConfiguration("camera_info_topic")
    frame_id = LaunchConfiguration("frame_id")

    return LaunchDescription([
        DeclareLaunchArgument("rgb_topic", default_value="/tof/color/image_raw"),
        DeclareLaunchArgument("depth_topic", default_value="/tof/depth/image_raw"),
        DeclareLaunchArgument("camera_info_topic", default_value="/tof/color/camera_info"),
        DeclareLaunchArgument("frame_id", default_value="base_link"),
        Node(
            package="loonar_limo_rgbd_odom",
            executable="rgbd_input_probe",
            name="rgbd_input_probe",
            output="screen",
            parameters=[{
                "rgb_topic": rgb_topic,
                "depth_topic": depth_topic,
                "camera_info_topic": camera_info_topic,
                "max_stamp_delta_s": 0.05,
                "min_valid_depth_ratio": 0.20,
            }],
        ),
        Node(
            package="rtabmap_sync",
            executable="rgbd_sync",
            name="loonar_rgbd_sync",
            output="screen",
            parameters=[{
                "approx_sync": True,
                "approx_sync_max_interval": 0.05,
                "topic_queue_size": 30,
                "sync_queue_size": 10,
                "qos": 2,
                "qos_camera_info": 2,
            }],
            remappings=[
                ("rgb/image", rgb_topic),
                ("depth/image", depth_topic),
                ("rgb/camera_info", camera_info_topic),
                ("rgbd_image", "/rgbd/image"),
            ],
        ),
        Node(
            package="rtabmap_odom",
            executable="rgbd_odometry",
            name="loonar_rgbd_odometry",
            output="screen",
            parameters=[{
                "frame_id": frame_id,
                "odom_frame_id": "rgbd_odom",
                "publish_tf": False,
                "subscribe_rgbd": True,
                "wait_for_transform": 0.2,
                "qos": 2,
                "topic_queue_size": 10,
                "sync_queue_size": 10,
                "max_update_rate": 10.0,
                "always_process_most_recent_frame": True,
                "publish_null_when_lost": True,
            }],
            remappings=[
                ("rgbd_image", "/rgbd/image"),
                ("odom", "/rgbd/odom"),
                ("odom_info", "/rgbd/odom_info"),
            ],
            # DaBai's measured useful depth interval is approximately
            # 0.36-2.5 m. Decimation bounds CPU use for the later Pi 5 port.
            arguments=[
                "--Odom/ImageDecimation", "2",
                "--Vis/MinDepth", "0.35",
                "--Vis/MaxDepth", "2.5",
                "--Vis/MinInliers", "12",
            ],
        ),
    ])
