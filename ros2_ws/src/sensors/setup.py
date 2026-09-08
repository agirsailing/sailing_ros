from setuptools import find_packages, setup
from glob import glob
import os

package_name = 'sensors'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), ['launch/sensors_launch.py']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='sumoth',
    maintainer_email='tech@agirsailing.se',
    description='ROS 2 nodes for Agir GPS, ultrasonic, IMU and battery sensors',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'gps_node = sensors.gps_node:main',
            'ultrasonic_node = sensors.ultrasonic_node:main',
            'ultrasonic_filter_node = sensors.ultrasonic_filter_node:main',
            'imu_node = sensors.imu_node:main',
            'battery_node = sensors.battery_node:main',
        ],
    },
)
