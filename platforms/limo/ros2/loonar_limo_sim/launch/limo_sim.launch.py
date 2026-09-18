"""LOONAR ROS-only SIL: LIMO four-wheel form, IMU/encoder, and ToF interface."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import Command, EnvironmentVariable, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = Path(get_package_share_directory("loonar_limo_sim"))
    xacro = PathJoinSubstitution([FindPackageShare("loonar_limo_sim"), "urdf", "limo_four_diff.urdf.xacro"])
    world = LaunchConfiguration("world")
    use_ekf = LaunchConfiguration("use_ekf")
    gui = LaunchConfiguration("gui")
    robot_description = Command([
        FindExecutable(name="xacro"), " ", xacro, " tof_x_m:=", LaunchConfiguration("tof_x_m"),
        " tof_y_m:=", LaunchConfiguration("tof_y_m"), " tof_z_m:=", LaunchConfiguration("tof_z_m"),
    ])
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value=str(share / "worlds" / "arena_terrain.world")),
        DeclareLaunchArgument("use_ekf", default_value="true"),
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("tof_x_m", default_value="0.08"),
        DeclareLaunchArgument("tof_y_m", default_value="0.0"),
        DeclareLaunchArgument("tof_z_m", default_value="0.10"),
        SetEnvironmentVariable("GAZEBO_MODEL_PATH", [str(share / "models"), ":", EnvironmentVariable("GAZEBO_MODEL_PATH", default_value="")]),
        # Do not rely on distro-specific gazebo.launch defaults: spawn_entity.py
        # requires the factory plugin to provide /spawn_entity.
        ExecuteProcess(cmd=["gzserver", "--verbose", world, "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so"], output="screen"),
        ExecuteProcess(cmd=["gzclient"], condition=IfCondition(gui), output="screen"),
        Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": robot_description, "use_sim_time": True}]),
        Node(package="gazebo_ros", executable="spawn_entity.py", arguments=["-topic", "robot_description", "-entity", "loonar_limo", "-x", "1.5", "-y", "-2.0", "-z", "0.16"], output="screen"),
        Node(package="loonar_limo_sim", executable="tof_depth_adapter", parameters=[{"use_sim_time": True}], output="screen"),
        Node(package="robot_localization", executable="ekf_node", name="ekf_filter_node", parameters=[str(share / "config" / "ekf.yaml"), {"use_sim_time": True}], condition=IfCondition(use_ekf)),
    ])
