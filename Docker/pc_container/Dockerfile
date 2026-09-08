FROM osrf/ros:jazzy-desktop-full

# Setup ros user
ARG USERNAME=ros
ARG USER_UID=1001
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME} 
RUN useradd -s /bin/bash --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} 
RUN mkdir /home/${USERNAME}/.config 
RUN chown ${USER_UID}:${USER_GID} /home/${USERNAME}/.config

# Setup sudo for ros user
RUN apt-get update \
    && apt-get install -y sudo \
    && echo ${USERNAME} ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME} \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
    apt-get install -y x11-apps

# install pip and fix SetuptoolsDeprecationWarning for latest python on ros2
ARG PIP_BREAK_SYSTEM_PACKAGES=1 

RUN apt-get update \
    && apt-get install -y python3-pip 

# make everything up to date
RUN apt-get update \
    && apt-get install -y ros-dev-tools \
    && apt-get -y upgrade 

RUN mkdir -p /home/ros/ros2_ws/src && \
    chmod 777 -R /home/ros/ros2_ws

# Copy the entrypoint and bashrc scripts so we have 
# our container's environment set up correctly
COPY entrypoint.sh /entrypoint.sh
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_cd/function/colcon_cd.sh" >> /home/${USERNAME}/.bashrc
RUN echo "export _colcon_cd_root=/opt/ros/${ROS_DISTRO}/" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash" >> /home/${USERNAME}/.bashrc
RUN echo "source /home/${USERNAME}/ros2_ws/install/local_setup.bash" >> /home/${USERNAME}/.bashrc
RUN echo "cd /home/${USERNAME}/ros2_ws" >> /home/${USERNAME}/.bashrc

# Set up entrypoint and default command
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["/bin/bash"]

# raspberry specific packages installation
RUN apt-get update && apt-get install -y \
    gpiod libgpiod-dev \
    i2c-tools libi2c-dev \
    gpsd gpsd-clients python3-gps \
    wget nano tree minicom \
    bluez bluetooth dbus rfkill

## ROS PACKAGES #####

# Raggruppiamo le installazioni in un unico layer per alleggerire l'immagine
RUN apt-get update && apt-get install -y \
    ros-${ROS_DISTRO}-joint-state-publisher-gui \
    ros-${ROS_DISTRO}-foxglove-bridge \
    ros-${ROS_DISTRO}-ros2-control \
    ros-${ROS_DISTRO}-ros2-controllers \
    ros-${ROS_DISTRO}-rviz-imu-plugin \
    ros-${ROS_DISTRO}-tf2 \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-tf2-geometry-msgs \
    ros-${ROS_DISTRO}-tf-transformations \
    ros-${ROS_DISTRO}-robot-localization \
    ros-${ROS_DISTRO}-ublox-gps \
    ros-${ROS_DISTRO}-imu-pipeline \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap \
    ros-${ROS_DISTRO}-plotjuggler-ros

# Installiamo paho-mqtt via pip per avere l'ultima versione (2.x)
# Usiamo --break-system-packages perché siamo in un container (ambiente controllato)
RUN pip3 install "paho-mqtt>=2.0.0" bleak pandas --break-system-packages