"""Start every live package pipeline, including the recording manager."""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('sensors'),
                                  'launch', 'live_sensors.launch.py']))),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('data_elaboration'),
                                  'launch', 'live_data_elaboration.launch.py']))),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('communication_web'),
                                  'launch', 'live_communication.launch.py']))),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('rosbag_manager'),
                                  'launch', 'live_rosbag_manager.launch.py']))),
    ])
