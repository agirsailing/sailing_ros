# Data elaboration

Consumes ROS sensor messages and publishes derived outputs under /processed/.
No node in this package opens serial, I2C or GPIO devices.

## Topics and messages

| Node | Inputs | Outputs |
| --- | --- | --- |
| ultrasonic_filter_node | /ultrasonic/left, /ultrasonic/right (Range), /processed/imu/data (Imu) | /processed/boat_height (sail_msgs/BoatHeight) |
| imu_mount_transformer_node (imu_transformer) | /imu/data (Imu) | /internal/imu/mounted (Imu, boat-aligned axes) |
| imu_node | /internal/imu/mounted and /internal/imu/aero_body (Imu), handled by separate callbacks | /processed/imu/data and /processed/imu/data/aero (Imu); /processed/imu/rpy and /processed/imu/rpy/aero (RollPitchYaw) |
| imu_aero_transformer_node (imu_transformer) | /processed/imu/data (Imu) | /internal/imu/aero_body (Imu, FRD body axes) |
| heading_node | /gps/data (GpsData), /compass/data (Vector3Stamped) | /processed/heading_deg (Float64), /processed/gps/summary (sail_msgs/GpsSummary) |
| battery_monitor_node | /battery/data (Bool) | /processed/battery/low (Bool) |

Configuration belongs in config/params.yaml. Output names belong in
config/endpoints.yaml and its generated Python module. Raw input names are
imported from sensors.generated.ros_endpoints. Parameters are declared and
assigned in one statement, with validation in _validate_parameters().

## Boat height: mounting and conventions

The reference O is a **fixed point on the boat's design waterline below the
centre of mass**, not the moving intersection with the actual water surface.
Height is the world-vertical distance of O above the local water plane.
It is signed: a submerged reference gives negative height.

Coordinates use boat FLU: X forward, Y left (port), Z up. Measure each sensor's
position [x, y, z] in metres from O, including the longitudinal bowsprit offset,
lateral offset and height above the design waterline. The zero positions in YAML
are **placeholders to replace with measured installation dimensions**. They do
not represent a calibrated installation.

Both sensors are on the bow. Positive lateral_tilt_deg points the beam left
from body-down; negative points right. Positive forward_tilt_deg tilts towards
the bow. With lateral angle a and forward angle b, the unit beam is:

    u = [sin(b), cos(b) sin(a), -cos(b) cos(a)]

Defaults are +15 degrees left, -15 degrees right, zero forward tilt. These are
central-ray approximations; sensor field of view is not an installation angle.
Both sensor instances are enabled in sensors/config/params.yaml. Port assignments
remain provisional.

imu_mount_transformer_node uses the published mounting TF to align measurements
to boat FLU before imu_node estimates attitude. The height estimator expects frame_robotic
(imu_link_flu by default), using the same axes as the mounting vectors.
Its attitude_frame_id checks the message frame name; it does not look up TF.
reference_frame_id identifies O in BoatHeight; the height node does not publish
that reference TF. IMU placement does not change the ultrasonic mounting origin.

## Projection formula

Let R rotate boat vectors into the gravity-aligned world, r_i be a sensor
position from O, d_i its slant range, and u_i its beam direction. A return on
locally horizontal water satisfies:

    0 = h + (R r_i).z + d_i (R u_i).z
    c_i = -(R u_i).z
    h_i = d_i c_i - (R r_i).z

The implementation uses the quaternion's third rotation-matrix row directly.
For roll phi and pitch theta this row is:

    v = [-sin(theta), cos(theta) sin(phi), cos(theta) cos(phi)]
    h_i = -dot(v, r_i + d_i u_i)

Thus yaw is irrelevant. For a lateral-only beam (b = 0):

    h_i = d_i cos(theta) cos(phi + a_i)
          + x_i sin(theta)
          - y_i cos(theta) sin(phi)
          - z_i cos(theta) cos(phi)

At level attitude: h_i = d_i cos(a_i) - z_i.
The longitudinal offset x_i therefore matters when pitching, even though it
does not affect level height. Positive ROS roll lowers the right side, so at
+15 degrees the right beam is vertical; at -15 degrees the left beam is vertical.

## Fusion and validity

Each valid range is corrected using its most recent preceding attitude sample
within max_attitude_age_s. A short attitude history handles delayed range
delivery. No attitude extrapolation or interpolation is performed. Samples must
be fresh against the node's ROS clock, and their frame IDs must match YAML.
Invalid/unavailable quaternions, out-of-range or non-finite distances, beams beyond
max_incidence_deg, duplicate/out-of-order ranges and stale inputs produce no new
height. There is no fallback to an assumed level attitude.

Each new usable range triggers output, optionally paired with the other side
when the measurement timestamps differ by no more than max_pair_dt_s and both
are fresh. Each candidate retains its own attitude correction.

    w_i = c_i ** incidence_weight_power
    h = sum(w_i h_i) / sum(w_i)

At level attitude the symmetric beams have equal weights. Heeling smoothly
favours the more vertical beam. A single valid sensor is sufficient. A missing
echo need not be an infinite distance; if acquisition stops publishing valid
returns, the old candidate ages out. Invalid new returns clear that side's
candidate immediately. If both sensors stop, height publication stops.

If candidate heights differ by more than max_disagreement_m, the more vertical
beam wins; an equal-incidence tie suppresses output. This and the incidence
weights are tunable heuristics, not measured statistical confidence. No temporal
moving average is applied. Output stamp is the triggering range's stamp and
frame_id is the configured boat reference, not a transducer.

The geometric model assumes a rigid mounting and locally horizontal water.
Waves, reflections away from the central beam, acoustic cross-talk and IMU
acceleration errors cannot be corrected by this projection alone. Validate
timing, beam behaviour and thresholds on water. ROS time must match sensor
timestamps; bag replay needs /clock and use_sim_time. Backwards ROS clock jumps
clear cached samples.

## IMU attitude, mounting and standards

/imu/data contains measured acceleration (m/s^2) and angular velocity (rad/s),
with orientation_covariance[0] = -1. sensors retains the chip's axes.
All mounting, estimation and convention conversion belong to data_elaboration.
The launch files now start the actual imu_transformer executable, as in Polimi.

The layout follows the Polimi can_bus configuration: named frames, a six-value
tf_offset [x, y, z, roll, pitch, yaw] in metres/degrees, tf_offset_aero, and
cov_orient/cov_vel/cov_acc. Actual mounting values remain placeholders.
The pipeline is:

    /imu/data
      -> imu_mount_transformer_node (ROS imu_transformer + mounting TF)
      -> /internal/imu/mounted
      -> imu_node (stationary/level calibration and attitude filter)
      -> /processed/imu/data
      -> imu_aero_transformer_node (ROS imu_transformer + FRD TF)
      -> /internal/imu/aero_body
      -> imu_node.publish_aero callback (world-reference conversion only)
      -> /processed/imu/data/aero

Both transformer instances are from the external imu_transformer package; there
is no local replacement for their mounting/body-axis rotation. They load
target_frame from params.yaml. Keep the mounting target equal to
imu_node.frame_robotic, and the aerodynamic target equal to imu_node.frame_aero. Their unused magnetometer ports are remapped to
private names, so the two instances do not share those ports.

The TF rotation is applied before the level-boat calibration. imu_node rejects
input in a different frame and does not apply the mounting rotation a second
time. TF publication remains in imu_node and is independent of receiving data,
so the mounting transformer can start before attitude estimation.
The two callbacks in imu_node have distinct input/output topics. The aerodynamic
callback never republishes on the robotic topic or updates its attitude filter,
so the return path through imu_aero_transformer_node is not a feedback loop.
All final IMU publishers and their configuration now belong to imu_node.

imu_node publishes three static transforms:
- frame_base -> frame_imu: actual sensor mounting position and orientation.
- frame_base -> frame_robotic: same position, axes parallel to boat FLU.
- frame_robotic -> frame_aero: same position, 180-degree roll (FRD axes).

Both processed frames remain at the physical IMU. Position is represented in
TF; acceleration is not relocated to the centre of mass. A lever-arm correction
would also require angular acceleration and centripetal terms.
For the current development stage, assume the IMU is close enough to the centre
of mass to neglect this effect. The zero mounting translation represents that
approximation; it is not a measured installation position.

| Output | Body axes | Orientation reference |
| --- | --- | --- |
| /processed/imu/data | FLU: forward, left, up | Local up-world; yaw zero at startup |
| /processed/imu/data/aero | FRD: forward, right, down | Local down-world; yaw zero at startup |

The robotic stream feeds height estimation and is the intended future EKF input.
The aerodynamic stream is separate and must not be fed to an ENU-assuming EKF.
For explicit angles, /processed/imu/rpy and /processed/imu/rpy/aero use
sail_msgs/RollPitchYaw with roll_deg, pitch_deg and yaw_deg in degrees.
The filter still computes in radians; sensor_msgs/Imu outputs retain quaternions
and angular velocity in rad/s. All outputs retain the input sample timestamp.
Both start at zero roll/pitch when level; yaw starts at zero after calibration.
Aerodynamic signs are positive right-side-down roll, bow-up pitch and right turn.
The RPY relation is (roll, -pitch, -yaw) within the usual Euler-angle range.
The aerodynamic callback unwraps successive yaw values across turns (requiring less
than 180 degrees between samples), skips duplicates and resets on backwards time.

Like the Polimi launch, the external imu_transformer changes the sensor/body
frame while retaining the world reference. To also preserve the explicitly
requested intuitive aerospace angles, the publish_aero callback in imu_node
changes only the remaining world reference. It copies transformed acceleration,
gyro and their
covariances unchanged. It transforms orientation and its world-frame covariance.

The combined operation is:

    A = Rx(pi)
    R_aero = A.T R_robotic A
    vector_aero = A.T vector_robotic
    covariance_aero = A.T covariance_robotic A

This local down-world reference is **not geographic NED**: it is not aligned to
north. The body-axis TF alone does not describe the orientation-reference change.
Do not pass the aero message through a body-only TF transform expecting to undo
the full convention conversion; use the already published robotic stream instead.

tf_offset_aero must represent colocated FLU/FRD axes; arbitrary physical mounting
belongs in tf_offset. Isotropic covariance values are configured in YAML; zeros
mean unknown uncertainty, not perfect accuracy. Set measured variances before
EKF tuning. Covariance matrices are transformed along with the vectors.

The existing complementary filter is still approximate during large rotations
or translational acceleration. Yaw integrates the gyro relative to startup and
can drift. No output is published during initial stationary/level calibration.
Backwards timestamps reset the estimator and its relative yaw.

## Navigation direction and GPS summary

heading_node selects GPS course over ground when speed is above the configured
threshold (0.5 m/s); otherwise it uses a magnetic bearing derived from compass
X/Y counts. Inputs must be fresh. Without usable input, heading_deg is NaN.
This is a selector, not full heading fusion or tilt compensation, and it does
not correct the IMU yaw. Course over ground can differ from bow heading because
of leeway and current. Compass axis signs, biases and offset need calibration.
Bearing is nominally degrees clockwise from north, unlike ROS yaw.

gps_summary now publishes sail_msgs/GpsSummary rather than text:
- latitude_deg, longitude_deg and sog_mps (SI metres/second, not knots).
- direction_deg (clockwise from north) and direction_source
  (DIRECTION_NONE, DIRECTION_GPS_COG or DIRECTION_COMPASS).
- fix_valid and direction_valid; unavailable numeric values are NaN.
- Header processing time, gps_stamp and direction_stamp for source freshness.

The 0.5 m/s threshold is a software selection rule in heading_node, not a
receiver command or a hardware switch. The GPS driver publishes NAV-PVT course
without applying that threshold. Missing GPS can coexist with a valid compass
direction; the validity flags distinguish this. Altitude, satellites, accuracy
and DOP remain in the raw GpsData message.

## Battery

The only battery input is a low-battery GPIO alarm. The monitor confirms it after
low_samples_required consecutive true samples (default 1). False clears the
published alarm. It cannot infer voltage, percentage, charging status or health.
The existing configurable shutdown policy remains, requested at most once per
run. Replay excludes this monitor, so recorded alarms do not request shutdown.
Host shutdown behaviour depends on container/system configuration.

## Recording and replay

There is no live CSV logging node. rosbag_manager independently starts a
ros2 bag recorder on a start-recording service request, with -a and -s mcap.
It records discovered visible topics (including new topics discovered later).
Hidden topics are not included by default. Merely starting the manager does
not start recording.

ROS messages stored in MCAP can be converted to CSV offline. The existing
tools/bag_replay_to_csv.py still targets older Polimi topic names and message
layouts; it must be adapted before exporting the current Agir streams.

live_data_elaboration.launch.py and the compatibility data_elaboration_launch.py
start six nodes, including both transformer instances. replay_data_elaboration.launch.py excludes the battery monitor.
The sensors replay launch still accesses hardware until that pipeline is
implemented. Rebuild sail_msgs and the workspace before using new interfaces.

## TODO / work to revisit

- Heading semantics: decide whether to publish GPS course over ground and bow
  heading separately, and whether/how to fuse them. Revisit the current 0.5 m/s
  selection threshold and transitions; validate compass mounting, calibration,
  tilt compensation and magnetic/true-north handling before claiming bow heading.
- Ultrasonic fusion: measure echo availability, noise and height error against
  an independent reference over the expected roll/pitch range. Use recorded bags
  to tune incidence_weight_power, max_incidence_deg and max_disagreement_m.
  The current cosine exponent of 8 is a heuristic, not a sensor noise model.
  Check wave effects, timing and acoustic cross-talk; keep geometric projection
  separate from reliability weighting.
- Installation: replace provisional ultrasonic positions/beam angles and verify
  the IMU mounting rotation. Keep the near-COM assumption for now; revisit lever-
  arm compensation only if the actual IMU offset and motion make it significant.
- IMU estimation / EKF: characterize covariance values and filter behaviour
  during manoeuvres. Decide later how to reference yaw to north; current yaw
  remains relative to startup. Use the robotic Imu stream for the future EKF.
- Replay / export: implement bag-driven replay without hardware acquisition and
  adapt CSV export to the current Agir topics and message definitions.

The ROS transformer package is declared as a runtime dependency. Both Dockerfiles
already install imu-pipeline; no Docker commands were run for this change.

## References

- ROS coordinate conventions:
  https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst
- Standard Imu message:
  https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/Imu.msg
- ROS bag recording:
  https://github.com/ros2/rosbag2/tree/jazzy

- imu_transformer orientation semantics (fixed since 0.3.1):
  https://docs.ros.org/en/jazzy/p/imu_transformer/__CHANGELOG.html
