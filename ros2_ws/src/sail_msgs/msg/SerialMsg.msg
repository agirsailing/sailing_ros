# Raw transport packet. Stamp is host reception time (synthetic time in test bags).
# frame_id is empty: a multiplexed packet has no single spatial reference frame.
std_msgs/Header header
uint8 id
std_msgs/UInt8MultiArray payload
