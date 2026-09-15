cmake_minimum_required(VERSION 3.8)
project(sail_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 1. Build dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

# 2. Message and service definitions
# Register every .msg and .srv file here.
set(msg_files
  "msg/BoatHeight.msg"
  "msg/RollPitchYaw.msg"
  "msg/GpsData.msg"
  "msg/GpsSummary.msg"
  "msg/SerialMsg.msg"
  "msg/Mark.msg"
  "msg/MapDataMsg.msg"
  "msg/RecordingState.msg"
)

set(srv_files
  "srv/StartRecording.srv"
  "srv/StopRecording.srv"
  "srv/ManageRecording.srv"
)

# 3. Generate the ROS interfaces
rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES std_msgs builtin_interfaces
)

# 4. Export the generated interface runtime
ament_export_dependencies(rosidl_default_runtime)
ament_package()
