# sail_msgs

ROS 2 interface package based on the Polimi Sailing Team definitions.
It contains 10 messages and 3 recording services:

- BatteryData
- SerialMsg
- Mark
- MapDataMsg
- RecordingState
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

Raw receiver data now uses the existing `gps_msgs/msg/GPSFix` type on `/gps/data`.
The former `GpsData.msg` has been removed; old raw GPS bags are not compatible
with the new subscribers. Clean-build the workspace after installing `gps_msgs`.
`GpsSummary` has also been removed: the gateway reads GPSFix and processed IMU
attitude directly, then prepares DashboardDataMsg and MapDataMsg.
`BoatHeight` has been replaced by `marti_common_msgs/msg/Float64Stamped` on
`/processed/boat_height`. Its `value` is signed vertical clearance in metres,
referenced to the design-waterline point below the centre of mass; the header
retains the measurement timestamp and boat reference. Rebuild consumers and
clean-build to remove the old interface.
`RollPitchYaw` is also removed: standard `sensor_msgs/Imu` carries orientation in
a quaternion. The gateway converts the aero Imu to dashboard angles and wraps yaw
to [0, 360) degrees. With BNO085 rotation_vector it references magnetic north;
game rotation vector / raw fallback has no north reference.

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
