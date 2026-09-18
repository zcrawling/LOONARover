"""LIMO profile for passive comparison; existing driver/EKF remain externally owned."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    profile = str(Path(get_package_share_directory('loonar_limo_localization'))/'config/slip_contact_shadow.yaml')
    return LaunchDescription([
        Node(package='loonar_localization', executable='primitive_manager', name='loonar_primitive_manager', output='screen'),
        Node(package='loonar_localization', executable='dead_reckoning', name='loonar_dead_reckoning', parameters=[profile], output='screen'),
        Node(package='loonar_localization', executable='stop_registration', name='loonar_stop_registration', parameters=[profile], output='screen'),
    ])
