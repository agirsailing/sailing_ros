"""Launch processing; replay never starts the shutdown policy."""

from data_elaboration.generated.ros_endpoints import Topics
from sensors.generated.ros_endpoints import Topics as SensorTopics

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
        Node(package='imu_transformer', executable='imu_transformer_node',
             name='imu_mount_transformer_node', parameters=[params], output='screen',
             remappings=[
                 ('imu_in', SensorTopics.I2C_SENSORS_NODE.PUB.IMU_DATA),
                 ('imu_out', Topics.IMU_MOUNT_TRANSFORMER_NODE.PUB.IMU_OUT),
                 ('mag_in', Topics.Shared.TRANSFORMER_MAG_IN),
                 ('mag_out', Topics.Shared.TRANSFORMER_MAG_OUT),
             ]),
        Node(package='imu_transformer', executable='imu_transformer_node',
             name='imu_aero_transformer_node', parameters=[params], output='screen',
             remappings=[
                 ('imu_in', Topics.IMU_AERO_TRANSFORMER_NODE.SUB.IMU_IN),
                 ('imu_out', Topics.IMU_AERO_TRANSFORMER_NODE.PUB.IMU_OUT),
                 ('mag_in', Topics.Shared.TRANSFORMER_MAG_IN),
                 ('mag_out', Topics.Shared.TRANSFORMER_MAG_OUT),
             ]),
        Node(package='data_elaboration', executable='heading_node',
             name='heading_node', parameters=[params], output='screen'),
    ])
