"""STOP-to-STOP translation correction using an existing DR/state producer."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('points_topic', default_value='/tof/depth/points'),
        DeclareLaunchArgument('publish_map_tf', default_value='false'),
        Node(package='loonar_localization', executable='stop_registration', output='screen',
             parameters=[{'registration_enabled': True, 'mode': 'gyro_yaw',
                          'publish_map_tf': ParameterValue(LaunchConfiguration('publish_map_tf'), value_type=bool)}],
             remappings=[('tof/depth/points', LaunchConfiguration('points_topic'))]),
    ])
