#!/usr/bin/env bash
set -e

source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
source /usr/share/colcon_cd/function/colcon_cd.sh
export _colcon_cd_root="/opt/ros/${ROS_DISTRO:-jazzy}/"
source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash

cd /home/ros/ros2_ws
if [[ -f install/setup.bash ]]; then
  source install/setup.bash
fi

if [[ "$#" -eq 0 ]]; then
  exec bash
else
  exec "$@"
fi
