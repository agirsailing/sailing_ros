from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'rosbag_manager'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        
        # Install launch files.
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        
        # Install YAML configuration alongside the package.
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ros',
    maintainer_email='ettoremugisha.cirillo@mail.polimi.it',
    description='Service-controlled MCAP recording for the Agir Sailing Team',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'rosbag_manager_node = rosbag_manager.rosbag_manager_node:main',
        ],
    },
)
