from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import TimerAction


def generate_launch_description():

    ultrasonic_left = Node(
        package="sensors_package",
        executable="talker_ultrasonic",
        name="ultrasonic_left",
        parameters=[{
            "port":      "/dev/ttyUSB0",
            "topic":     "ctrl_raw_left",
            "device_id": "ultrasonic_left",
        }],
    )

    ultrasonic_right = Node(
        package="sensors_package",
        executable="talker_ultrasonic",
        name="ultrasonic_right",
        parameters=[{
            "port":      "/dev/ttyUSB1",
            "topic":     "ctrl_raw_right",
            "device_id": "ultrasonic_right",
        }],
    )

    ultrasonic_filter = Node(
        package="sensors_package",
        executable="talker_filter_ultrasonic",
        name="ultrasonic_filter_node",
    )

    battery = Node(
        package="sensors_package",
        executable="talker_bat",
        name="battery_node",
    )

    gps = Node(
        package="sensors_package",
        executable="talker_gps",
        name="gps_node",
    )

    imu = Node(
        package="sensors_package",
        executable="talker_imu",
        name="imu_node",
    )

    return LaunchDescription([
        ultrasonic_left,
        ultrasonic_right,
        ultrasonic_filter,
        battery,
        gps,
        imu,
    ])