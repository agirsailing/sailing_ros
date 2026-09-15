# sail_msgs

ROS 2 interface package based on the Polimi Sailing Team definitions: 5 messages
(`SerialMsg`, `Mark`, `MapDataMsg`, `RecordingState`, `GpsData`) and 3 recording services.
The retained interface names, fields, types and constants are preserved,
including the original `COMITATO` and `BOLINA` constants in `Mark.msg`.

The workspace build script builds this package first so its generated interfaces
are available to the remaining packages. Add new interface files to
`CMakeLists.txt` and declare any new dependencies in `package.xml`.

`GpsData` carries the Agir receiver solution with explicit units and fix validity,
before any compass fusion. It replaces parsing a string in processing nodes.
