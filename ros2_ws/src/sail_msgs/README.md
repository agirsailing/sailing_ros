# sail_msgs

ROS 2 interface package based on the Polimi Sailing Team definitions.
It contains 8 messages and 3 recording services:

- SerialMsg
- Mark
- MapDataMsg
- RecordingState
- GpsData
- GpsSummary
- BoatHeight
- RollPitchYaw

Existing interface names, fields and constants are preserved, including the
original COMITATO and BOLINA constants in Mark.msg.

GpsData carries the Agir receiver solution with explicit units and fix validity,
before compass selection. GpsSummary carries structured position, SOG in m/s,
selected direction, source and validity flags, with separate source timestamps. BoatHeight carries the timestamped, signed vertical clearance of the design-
waterline reference below the centre of mass, estimated from left/right ranges
and attitude, in metres. RollPitchYaw carries timestamped roll_deg, pitch_deg and yaw_deg;
the topic selects robotic FLU/up-world or aerodynamic FRD/down-world convention.
Yaw is relative to initialization and is not an absolute compass heading.

The workspace build script builds this package first so its generated interfaces
are available to the remaining packages. Add new interfaces to CMakeLists.txt
and declare any new dependencies in package.xml.
