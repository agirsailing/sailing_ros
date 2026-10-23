from setuptools import find_packages, setup


setup(
    name='sail_common',
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/sail_common']),
        ('share/sail_common', ['package.xml', 'README.md']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Agir Sailing Team',
    maintainer_email='tech@agirsailing.se',
    description='Shared timing utilities for Agir ROS nodes',
    license='Apache-2.0',
    extras_require={'test': ['pytest']},
)
