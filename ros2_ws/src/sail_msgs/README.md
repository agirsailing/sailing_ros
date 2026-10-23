# sail_msgs

ROS 2 interface package based on the Polimi Sailing Team definitions.
It contains 10 messages and 3 recording services:

- BatteryData
- SerialMsg
- Mark
- MapDataMsg
- RecordingState
- GpsData
- GpsSummary
- BoatHeight
- RollPitchYaw
- DashboardDataMsg

In Agir, `SerialMsg` is currently used only by `ros2_ws/tools/gen_bag_test.py`
to write synthetic raw packets to `/serial/raw_rx` in test bags. No live Agir
node publishes or subscribes to it. It contains `header`, a packet `id` and byte
`payload`; ultrasound acquisition publishes `sensor_msgs/Range` directly instead.

All measurement/telemetry messages use `std_msgs/Header header`, including raw
`SerialMsg` packets. Header timestamps keep their documented acquisition or
snapshot meaning. GPS source timestamps (`gps_stamp`, `direction_stamp`) remain
additional fields: they identify the original inputs, not the aggregate's age.
`Mark` describes a course landmark and `RecordingState` describes recorder state;
neither is a sensor measurement, so their existing interfaces are unchanged.

`SerialMsg.stamp` has moved to `SerialMsg.header.stamp`. The test bag generator
uses the new field and leaves `header.frame_id` empty for multiplexed packets.
Rebuild `sail_msgs` and its consumers together. Old SerialMsg bags and external
producers/readers using the former layout need conversion or the old interface;
they are not wire-compatible with the new layout. This does not change the
dashboard/map MQTT payloads or any existing live measurement interface.

DashboardDataMsg is the dashboard snapshot. MapDataMsg replaces the unused
legacy map definition with the position snapshot actually consumed by Agir.
The original COMITATO and BOLINA constants in Mark.msg are preserved.

GpsData carries the Agir receiver solution with explicit units and fix validity,
before compass selection. GpsSummary carries structured position, SOG in m/s,
selected direction, source and validity flags, with separate source timestamps. BoatHeight carries the timestamped, signed vertical clearance of the design-
waterline reference below the centre of mass, estimated from left/right ranges
and attitude, in metres. RollPitchYaw carries timestamped roll_deg, pitch_deg and yaw_deg;
the topic selects robotic FLU/up-world or aerodynamic FRD/down-world convention.
Yaw is relative to initialization and is not an absolute compass heading.

DashboardDataMsg aggregates aerospace angles in degrees, waterline-reference height
in metres, raw left/right ultrasonic beam distances (`ultrasonic_left_m` and
`ultrasonic_right_m`), battery voltage, a low-battery alarm and SOG in m/s, with independent validity flags.
MapDataMsg contains latitude/longitude in degrees, SOG in m/s and GPS validity.
Both carry a snapshot timestamp; MapDataMsg also preserves the source GPS stamp.
The communication gateway converts unavailable floating-point values from ROS NaN
to JSON null for the web app.

The workspace build script builds this package first so its generated interfaces
are available to the remaining packages. Add new interfaces to CMakeLists.txt
and declare any new dependencies in package.xml.
