FROM ros:jazzy-ros-core-noble

# Set these build arguments to match the workspace owner on Linux.
ARG USERNAME=ros
ARG USER_UID=1001
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd -s /bin/bash --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
    && mkdir -p /home/${USERNAME}/.config /home/${USERNAME}/ros2_ws/src \
    && chown -R ${USER_UID}:${USER_GID} /home/${USERNAME}

# Development tools and Python libraries imported by the current sensor nodes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo ros-dev-tools python3-pip \
    python3-serial python3-smbus2 python3-lgpio \
    x11-apps \
    gpiod libgpiod-dev \
    i2c-tools libi2c-dev \
    gpsd gpsd-clients python3-gps \
    wget nano tree minicom \
    bluez bluetooth dbus rfkill \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME} \
    && rm -rf /var/lib/apt/lists/*

# Keep the original system update and CMake tooling for future packages.
RUN apt-get update && apt-get -y upgrade \
    && apt-get install -y \
    ros-${ROS_DISTRO}-ament-cmake \
    ros-${ROS_DISTRO}-ament-cmake-auto \
    && rm -rf /var/lib/apt/lists/*

# Wayland's runtime directory must belong to the container user.
RUN mkdir -p /tmp/runtime-ros \
    && chown ${USER_UID}:${USER_GID} /tmp/runtime-ros \
    && chmod 700 /tmp/runtime-ros

# ROS dependencies used by sensors and its Python launch file.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-rclpy \
    ros-${ROS_DISTRO}-std-msgs \
    ros-${ROS_DISTRO}-sensor-msgs \
    ros-${ROS_DISTRO}-geometry-msgs \
    ros-${ROS_DISTRO}-launch-ros \
    && rm -rf /var/lib/apt/lists/*

# Optional packages inherited from the Polimi template; no current node uses them.
# Some may already be included transitively in the base image.
# Uncomment this entire RUN block only when the corresponding features are added.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     ros-${ROS_DISTRO}-joint-state-publisher-gui \
#     ros-${ROS_DISTRO}-foxglove-bridge \
#     ros-${ROS_DISTRO}-ros2-control \
#     ros-${ROS_DISTRO}-ros2-controllers \
#     ros-${ROS_DISTRO}-rviz-imu-plugin \
#     ros-${ROS_DISTRO}-tf2 \
#     ros-${ROS_DISTRO}-tf2-ros \
#     ros-${ROS_DISTRO}-tf2-geometry-msgs \
#     ros-${ROS_DISTRO}-tf-transformations \
#     ros-${ROS_DISTRO}-robot-localization \
#     ros-${ROS_DISTRO}-rosbridge-server \
#     ros-${ROS_DISTRO}-rosbag2 \
#     ros-${ROS_DISTRO}-rosbag2-storage-default-plugins \
#     ros-${ROS_DISTRO}-rosbag2-storage-sqlite3 \
#     ros-${ROS_DISTRO}-rosbag2-storage-mcap \
#     ros-${ROS_DISTRO}-rosbag2-compression-zstd \
#     ros-${ROS_DISTRO}-rqt-common-plugins \
#     ros-${ROS_DISTRO}-rqt-action \
#     ros-${ROS_DISTRO}-rqt-graph \
#     ros-${ROS_DISTRO}-rqt-topic \
#     ros-${ROS_DISTRO}-rqt-service-caller \
#     ros-${ROS_DISTRO}-rqt-publisher \
#     ros-${ROS_DISTRO}-rqt-shell \
#     ros-${ROS_DISTRO}-rqt-console \
#     ros-${ROS_DISTRO}-rqt-plot \
#     ros-${ROS_DISTRO}-rqt-tf-tree \
#     ros-${ROS_DISTRO}-ublox-gps \
#     ros-${ROS_DISTRO}-imu-pipeline \
#     && rm -rf /var/lib/apt/lists/*

# The current GPS node reads UBX directly through pyubx2.
RUN pip3 install --no-cache-dir --break-system-packages pyubx2

# Keep the original MQTT and Bluetooth Python integrations.
RUN pip3 install --no-cache-dir --break-system-packages "paho-mqtt>=2.0.0" bleak

COPY entrypoint.sh /entrypoint.sh
# Normalize line endings even when the repository was checked out on Windows.
RUN sed -i 's/\r$//' /entrypoint.sh
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_cd/function/colcon_cd.sh" >> /home/${USERNAME}/.bashrc
RUN echo "export _colcon_cd_root=/opt/ros/${ROS_DISTRO}/" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash" >> /home/${USERNAME}/.bashrc
RUN echo '[ -f ~/ros2_ws/install/setup.bash ] && source ~/ros2_ws/install/setup.bash' >> /home/${USERNAME}/.bashrc
RUN echo "cd /home/${USERNAME}/ros2_ws" >> /home/${USERNAME}/.bashrc

WORKDIR /home/${USERNAME}/ros2_ws
USER ${USERNAME}
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["/bin/bash"]
