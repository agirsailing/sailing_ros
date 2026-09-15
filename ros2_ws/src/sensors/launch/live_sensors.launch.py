"""Launch hardware acquisition, including IMU and compass via one mux owner."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = LaunchConfiguration('sensors_params_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'sensors_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('sensors'), 'config', 'params.yaml'])),
        Node(package='sensors', executable='ultrasonic_node',
             name='ultrasonic_front_node', parameters=[params], output='screen'),
        Node(package='sensors', executable='ultrasonic_node',
             name='ultrasonic_back_node', parameters=[params], output='screen'),
        Node(package='sensors', executable='gps_node',
             name='gps_node', parameters=[params], output='screen'),
        Node(package='sensors', executable='i2c_sensors_node',
             name='i2c_sensors_node', parameters=[params], output='screen'),
        Node(package='sensors', executable='battery_node',
             name='battery_node', parameters=[params], output='screen'),
    ])
