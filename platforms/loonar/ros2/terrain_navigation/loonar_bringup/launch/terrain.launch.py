"""Independent node switches. Observation-only by default; no hardware auto-start."""

from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import (
    LaunchConfiguration,
    Command,
    FindExecutable,
    EnvironmentVariable,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    share = Path(get_package_share_directory("loonar_bringup"))
    arguments = [
        DeclareLaunchArgument(
            "params_file", default_value=str(share / "config/terrain.yaml")
        ),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("enable_motion", default_value="false"),
        DeclareLaunchArgument("calibration_confirmed", default_value="false"),
        DeclareLaunchArgument("autostart", default_value="false"),
        DeclareLaunchArgument("gcs_auto_start", default_value="false"),
        DeclareLaunchArgument("publish_tf", default_value="false"),
        DeclareLaunchArgument(
            "robot_description_file",
            default_value=str(share / "urdf/loonar.urdf.xacro"),
        ),
    ]
    nodes = []
    for name, package, exe, default in [
        ("adapter", "loonar_tof_adapter", "tof_adapter", "true"),
        ("stationary", "loonar_stationary_detector", "stationary_detector", "true"),
        ("perception", "loonar_terrain_perception", "terrain_perception", "true"),
        ("planner", "loonar_terrain_planner", "terrain_planner", "true"),
        ("motion", "loonar_motion_primitives", "motion_primitives", "true"),
        ("navigator", "loonar_terrain_navigator", "terrain_navigator", "true"),
        ("safety", "loonar_safety_monitor", "safety_monitor", "true"),
        ("base_io", "loonar_bringup", "base_io", "false"),
    ]:
        arguments.append(DeclareLaunchArgument("run_" + name, default_value=default))
        nodes.append(
            Node(
                package=package,
                executable=exe,
                output="screen",
                condition=IfCondition(LaunchConfiguration("run_" + name)),
                parameters=[
                    LaunchConfiguration("params_file"),
                    {
                        k: ParameterValue(LaunchConfiguration(k), value_type=bool)
                        for k in (
                            "use_sim_time",
                            "enable_motion",
                            "calibration_confirmed",
                            "autostart",
                            "gcs_auto_start",
                        )
                    },
                ],
            )
        )
    nodes.append(
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            condition=IfCondition(LaunchConfiguration("publish_tf")),
            parameters=[
                {
                    "use_sim_time": ParameterValue(
                        LaunchConfiguration("use_sim_time"), value_type=bool
                    ),
                    "robot_description": ParameterValue(
                        Command(
                            [
                                FindExecutable(name="xacro"),
                                " ",
                                LaunchConfiguration("robot_description_file"),
                            ]
                        ),
                        value_type=str,
                    ),
                }
            ],
        )
    )
    # Load before creating DDS participants; preserve an explicitly chosen
    # profile. Full-resolution float images need more than the default SHM size.
    transport = SetEnvironmentVariable(
        "FASTRTPS_DEFAULT_PROFILES_FILE",
        EnvironmentVariable(
            "FASTRTPS_DEFAULT_PROFILES_FILE",
            default_value=str(share / "config/fastdds.xml"),
        ),
    )
    return LaunchDescription(arguments + [transport] + nodes)
