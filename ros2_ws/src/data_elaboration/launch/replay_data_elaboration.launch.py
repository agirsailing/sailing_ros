"""Launch processing; replay never starts the shutdown policy."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = LaunchConfiguration('data_elaboration_params_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'data_elaboration_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('data_elaboration'), 'config', 'params.yaml'])),
        Node(package='data_elaboration', executable='ultrasonic_filter_node',
             name='ultrasonic_filter_node', parameters=[params], output='screen'),
        Node(package='data_elaboration', executable='imu_node',
             name='imu_node', parameters=[params], output='screen'),
        Node(package='data_elaboration', executable='heading_node',
             name='heading_node', parameters=[params], output='screen'),
        Node(package='data_elaboration', executable='csv_logger_node',
             name='csv_logger_node', parameters=[params], output='screen'),
    ])
