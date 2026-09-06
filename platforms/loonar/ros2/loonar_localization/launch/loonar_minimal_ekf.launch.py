"""Launch only the LOONAR local-odometry EKF.

The RS485 bridge must already publish /wheel/odom and the BNO085 driver must
already publish /imu/data. robot_state_publisher must publish the fixed
base_link -> imu_link transform separately. This launch sends no command and
does not publish any static transform.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("loonar_localization"))
    return LaunchDescription([
        Node(
            package="robot_localization",
            executable="ekf_node",
            name="ekf_filter_node",
            output="screen",
            parameters=[str(share / "config" / "loonar_minimal_ekf.yaml")],
        ),
    ])
