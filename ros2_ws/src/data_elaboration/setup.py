from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'data_elaboration'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Agir Sailing Team',
    maintainer_email='tech@agirsailing.se',
    description='Sensor data processing for the Agir Sailing Team',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'ultrasonic_filter_node = data_elaboration.ultrasonic_filter_node:main',
            'imu_node = data_elaboration.imu_node:main',
            'heading_node = data_elaboration.heading_node:main',
            'battery_monitor_node = data_elaboration.battery_monitor_node:main',
            'csv_logger_node = data_elaboration.csv_logger_node:main',
        ],
    },
)
