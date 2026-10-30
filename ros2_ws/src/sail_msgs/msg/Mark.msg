# One saved course mark. Header stamp is the captured GPS sample time.
uint8 COMMITTEE=0
uint8 PIN=1
uint8 WINDWARD=2

std_msgs/Header header
uint8 type
# WGS84 degrees; double precision preserves the original GPS coordinates.
float64 lat
float64 lon
