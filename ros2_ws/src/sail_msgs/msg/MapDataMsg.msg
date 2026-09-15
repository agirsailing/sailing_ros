# ros2_ws/src/sail_msgs/msg/MapDataMsg.msg

builtin_interfaces/Time stamp
float32 lat
float32 lon
float32 yaw
float32 twd
float32 tws
float32 dtl   # Perpendicular distance to the line, in metres.
float32 ttl   # Time to the line, in seconds.
sail_msgs/Mark[] marks
