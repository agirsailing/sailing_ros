FROM ros:jazzy-ros-core-noble

# Create the ROS user.
ARG USERNAME=ros
ARG USER_UID=1001
ARG USER_GID=${USER_UID}

RUN groupadd --gid ${USER_GID} ${USERNAME}
RUN useradd -s /bin/bash --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME}
RUN mkdir /home/${USERNAME}/.config
RUN chown ${USER_UID}:${USER_GID} /home/${USERNAME}/.config

# Install sudo and allow the ROS user to administer the container.
RUN apt-get update \
    && apt-get install -y --install-recommends sudo \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME} \
    && rm -rf /var/lib/apt/lists/*

# Install X11 tools for graphical applications.
RUN apt-get update \
    && apt-get install -y --install-recommends x11-apps \
    && rm -rf /var/lib/apt/lists/*

# Install pip for Python dependencies.
RUN apt-get update \
    && apt-get install -y --install-recommends python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install ROS development tools and update system packages.
RUN apt-get update \
    && apt-get install -y --install-recommends ros-dev-tools \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/*

# Install CMake build support for the ROS core image.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-ament-cmake \
    ros-${ROS_DISTRO}-ament-cmake-auto \
    && rm -rf /var/lib/apt/lists/*

# Create a workspace writable by all container users.
RUN mkdir -p /home/${USERNAME}/ros2_ws/src \
    && chmod 777 -R /home/${USERNAME}/ros2_ws

# Install GPIO and I2C tools and development libraries.
RUN apt-get update \
    && apt-get install -y --install-recommends gpiod libgpiod-dev i2c-tools libi2c-dev \
    && rm -rf /var/lib/apt/lists/*

# Install GPS daemon, clients and Python bindings.
RUN apt-get update \
    && apt-get install -y --install-recommends gpsd gpsd-clients python3-gps \
    && rm -rf /var/lib/apt/lists/*

# Install command-line tools for development and serial diagnostics.
RUN apt-get update \
    && apt-get install -y --install-recommends wget nano tree minicom \
    && rm -rf /var/lib/apt/lists/*

# Install Bluetooth services and utilities.
RUN apt-get update \
    && apt-get install -y --install-recommends bluez bluetooth dbus rfkill \
    && rm -rf /var/lib/apt/lists/*

# Install ROS Python, message and launch dependencies explicitly.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-rclpy \
    ros-${ROS_DISTRO}-std-msgs \
    ros-${ROS_DISTRO}-sensor-msgs \
    ros-${ROS_DISTRO}-geometry-msgs \
    ros-${ROS_DISTRO}-launch-ros \
    && rm -rf /var/lib/apt/lists/*

# Install ROS control and transform packages.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-ros2-control \
    ros-${ROS_DISTRO}-ros2-controllers \
    ros-${ROS_DISTRO}-tf2 \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-tf2-geometry-msgs \
    ros-${ROS_DISTRO}-tf-transformations \
    && rm -rf /var/lib/apt/lists/*

# Install ROS localization and sensor processing packages.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-robot-localization \
    ros-${ROS_DISTRO}-ublox-gps \
    ros-${ROS_DISTRO}-imu-pipeline \
    && rm -rf /var/lib/apt/lists/*

# Install ROS visualization and web bridges.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-joint-state-publisher-gui \
    ros-${ROS_DISTRO}-rviz-imu-plugin \
    ros-${ROS_DISTRO}-foxglove-bridge \
    ros-${ROS_DISTRO}-rosbridge-server \
    && rm -rf /var/lib/apt/lists/*

# Install ROS bag recording, storage formats and compression.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-rosbag2 \
    ros-${ROS_DISTRO}-rosbag2-storage-default-plugins \
    ros-${ROS_DISTRO}-rosbag2-storage-sqlite3 \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap \
    ros-${ROS_DISTRO}-rosbag2-compression-zstd \
    && rm -rf /var/lib/apt/lists/*

# Install rqt tools for ROS graph inspection and diagnostics.
RUN apt-get update && apt-get install -y --install-recommends \
    ros-${ROS_DISTRO}-rqt-common-plugins \
    ros-${ROS_DISTRO}-rqt-action \
    ros-${ROS_DISTRO}-rqt-graph \
    ros-${ROS_DISTRO}-rqt-topic \
    ros-${ROS_DISTRO}-rqt-service-caller \
    ros-${ROS_DISTRO}-rqt-publisher \
    ros-${ROS_DISTRO}-rqt-shell \
    ros-${ROS_DISTRO}-rqt-console \
    ros-${ROS_DISTRO}-rqt-plot \
    ros-${ROS_DISTRO}-rqt-tf-tree \
    && rm -rf /var/lib/apt/lists/*

# Install Python integrations for MQTT and Bluetooth.
RUN pip3 install --no-cache-dir --break-system-packages "paho-mqtt>=2.0.0" bleak

# Agir sensor dependencies: serial, I2C and GPIO Python libraries.
RUN apt-get update \
    && apt-get install -y --install-recommends python3-serial python3-smbus2 python3-lgpio \
    && rm -rf /var/lib/apt/lists/*

# Agir GPS driver: read UBX messages directly in Python.
RUN pip3 install --no-cache-dir --break-system-packages pyubx2

# Prepare the private runtime directory used by Wayland applications.
# Compose mounts the host socket at /tmp/runtime-ros/wayland-0.
RUN mkdir -p /tmp/runtime-ros \
    && chown ${USER_UID}:${USER_GID} /tmp/runtime-ros \
    && chmod 700 /tmp/runtime-ros

# Copy the entrypoint after dependencies to preserve their build cache.
COPY entrypoint.sh /entrypoint.sh

# Normalize Windows line endings in the entrypoint.
RUN sed -i 's/\r$//' /entrypoint.sh

# Configure ROS and colcon for interactive shells.
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_cd/function/colcon_cd.sh" >> /home/${USERNAME}/.bashrc
RUN echo "export _colcon_cd_root=/opt/ros/${ROS_DISTRO}/" >> /home/${USERNAME}/.bashrc
RUN echo "source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash" >> /home/${USERNAME}/.bashrc

# Load the workspace only after it has been built.
RUN echo '[ -f ~/ros2_ws/install/setup.bash ] && source ~/ros2_ws/install/setup.bash' >> /home/${USERNAME}/.bashrc
RUN echo "cd /home/${USERNAME}/ros2_ws" >> /home/${USERNAME}/.bashrc

# Set the default workspace, user and startup command.
WORKDIR /home/${USERNAME}/ros2_ws
USER ${USERNAME}
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["/bin/bash"]
