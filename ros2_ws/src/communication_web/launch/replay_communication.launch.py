"""Launch telemetry only: replay must not control live recordings."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def check_mqtt_config(context):
    path = LaunchConfiguration('communication_web_mqtt_config_file').perform(context)
    if not Path(path).is_file():
        raise RuntimeError(
            'Missing MQTT config. Copy config/mqtt_config.example.yaml to '
            'config/mqtt_config.yaml, configure it and rebuild, or pass '
            'communication_web_mqtt_config_file:=/absolute/path/mqtt_config.yaml')
    return []


def generate_launch_description():
    params = LaunchConfiguration('communication_web_params_file')
    mqtt_config = LaunchConfiguration('communication_web_mqtt_config_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'communication_web_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('communication_web'), 'config', 'params.yaml'])),
        DeclareLaunchArgument(
            'communication_web_mqtt_config_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('communication_web'), 'config', 'mqtt_config.yaml'])),
        OpaqueFunction(function=check_mqtt_config),
        Node(package='communication_web', executable='telemetry_gateway_node',
             name='telemetry_gateway_node',
             parameters=[params, mqtt_config],
             output='screen'),
    ])
