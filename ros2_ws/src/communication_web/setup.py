from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'communication_web'

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
    description='Web communication for the Agir Sailing Team',
    license='Apache-2.0',
    entry_points={
        # Register future nodes as: name_node = package_name.name_node:main
        'console_scripts': [],
    },
)
