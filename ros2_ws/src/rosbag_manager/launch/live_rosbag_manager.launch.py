# /ros2_ws/src/rosbag_manager/launch/live_rosbag_manager.launch.py
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():

    # Locate the installed parameter file.
    config = os.path.join(
        get_package_share_directory('rosbag_manager'),
        'config',
        'params.yaml'
    )

    # === RosbagManager ===
    rosbag_manager_node = Node(
        package='rosbag_manager',
        executable='rosbag_manager_node',
        name='rosbag_manager_node',
        output='screen',
        parameters=[config]
    )
    
    return LaunchDescription([
        rosbag_manager_node
    ])
