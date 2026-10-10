"""Publish mount TFs only; no motion, fake joints, odom, or map publisher."""
from pathlib import Path
import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

DEFAULTS = {
    'imu_xyz':'0.03575 0 -0.057',
    'imu_rpy':'0 0 1.5707963267948966',
    'tof_xyz':'0.03575 0.0000500000471 -0.0075',
    'tof_rpy':'-1.5707963267948966 0 0',
    'publish_optical_frames':'false',
    'tof_optical_offset':'0.01599 0 0',
    'camera_optical_xyz':'0 0 0',
    'camera_optical_rpy':'0 0 0',
}


def start(context):
    path = Path(get_package_share_directory('loonar_description'))/'urdf/loonar.urdf.xacro'
    mappings = {k:LaunchConfiguration(k).perform(context) for k in DEFAULTS}
    description = xacro.process_file(str(path), mappings=mappings).toxml()
    return [LogInfo(msg='CAD mount TFs: IMU position is nominal; optical calibration remains unmeasured. Wheel TFs require measured /joint_states.'),
            Node(package='robot_state_publisher', executable='robot_state_publisher',
                 name='loonar_robot_state_publisher',
                 parameters=[{'robot_description':description}], output='screen')]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument(k,default_value=v) for k,v in DEFAULTS.items()]
                             + [OpaqueFunction(function=start)])
