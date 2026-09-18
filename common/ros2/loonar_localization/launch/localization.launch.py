"""Read-only shadow localization by default. Does not launch the vehicle driver."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    flags = ['publish_odom_tf','registration_enabled','publish_map_tf']
    return LaunchDescription([
        *[DeclareLaunchArgument(f, default_value='false') for f in flags],
        Node(package='loonar_localization', executable='primitive_manager', output='screen'),
        Node(package='loonar_localization', executable='dead_reckoning', output='screen',
             parameters=[{'publish_odom_tf': ParameterValue(LaunchConfiguration('publish_odom_tf'), value_type=bool)}]),
        Node(package='loonar_localization', executable='stop_registration', output='screen',
             parameters=[{f: ParameterValue(LaunchConfiguration(f), value_type=bool) for f in flags[1:]}]),
    ])
