# Structured navigation summary. Header stamp is processing time.
# Source timestamps allow consumers to distinguish reused and new inputs.
std_msgs/Header header
builtin_interfaces/Time gps_stamp
builtin_interfaces/Time direction_stamp

# Position and speed are NaN when fix_valid is false.
bool fix_valid
float64 latitude_deg
float64 longitude_deg
float64 sog_mps

# Direction is degrees clockwise from north, NaN when unavailable.
# GPS_COG is direction of motion, not necessarily bow heading.
uint8 DIRECTION_NONE=0
uint8 DIRECTION_GPS_COG=1
uint8 DIRECTION_COMPASS=2
bool direction_valid
uint8 direction_source
float64 direction_deg
