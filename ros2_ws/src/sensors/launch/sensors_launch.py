from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = PathJoinSubstitution([
        FindPackageShare('sensors'), 'config', 'params.yaml',
    ])

    return LaunchDescription([
        Node(
            package='sensors',
            executable='ultrasonic_node',
            name='ultrasonic_left_node',
            parameters=[params_file],
        ),
        Node(
            package='sensors',
            executable='ultrasonic_node',
            name='ultrasonic_right_node',
            parameters=[params_file],
        ),
        Node(
            package='sensors',
            executable='ultrasonic_filter_node',
            name='ultrasonic_filter_node',
        ),
        Node(
            package='sensors',
            executable='gps_node',
            name='gps_node',
        ),
        Node(
            package='sensors',
            executable='battery_node',
            name='battery_node',
        )
    ])
