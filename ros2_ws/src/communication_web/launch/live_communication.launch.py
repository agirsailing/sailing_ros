"""Launch telemetry and recording commands for live operation."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = LaunchConfiguration('communication_web_params_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'communication_web_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('communication_web'), 'config', 'params.yaml'])),
        Node(package='communication_web', executable='telemetry_gateway_node',
             name='telemetry_gateway_node', parameters=[params], output='screen'),
        Node(package='communication_web', executable='command_gateway_node',
             name='command_gateway_node', parameters=[params], output='screen'),
    ])
