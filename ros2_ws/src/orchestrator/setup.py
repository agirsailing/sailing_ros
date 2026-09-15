from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'orchestrator'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Agir Sailing Team',
    maintainer_email='tech@agirsailing.se',
    description='Top-level live and replay launch files for the Agir Sailing Team',
    license='Apache-2.0',
    entry_points={'console_scripts': []},
)
