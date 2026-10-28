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

Each sensor uses one `mounting` array:
`[x_m, y_m, z_m, lateral_tilt_deg, forward_tilt_deg]`.
For example, `left.mounting: [2.0, 0.2, 0.6, 15.0, 0.0]` means 2 m forward,
0.2 m left and 0.6 m above O, with a 15-degree leftward beam tilt and no forward
tilt. Use decimal values for all five entries (ROS double array). Custom parameter
files must replace the former separate position and tilt parameters with this array.

Both sensors are on the bow. Positive lateral_tilt_deg points the beam left
from body-down; negative points right. Positive forward_tilt_deg tilts towards
the bow. With lateral angle a and forward angle b, the unit beam is:

    u = [sin(b), cos(b) sin(a), -cos(b) cos(a)]

Defaults are +1 degree left, -1 degree right, zero forward tilt. These are
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

The UART BNO085 now publishes acceleration (m/s^2, including gravity), angular
velocity (rad/s) and onboard fused orientation on `/imu/data`. The sensor's
`rotation_vector` uses its internal accelerometer, gyro and magnetometer; the
separate compass is not fed into this firmware fusion.

The existing mounting pipeline is preserved:

    /imu/data -> imu_mount_transformer_node -> /internal/imu/mounted
      -> imu_node -> /processed/imu/data (+ /processed/imu/rpy)
      -> imu_aero_transformer_node -> /internal/imu/aero_body
      -> imu_node aero callback -> /processed/imu/data/aero (+ /processed/imu/rpy/aero)

Both transformers are instances of the external ROS `imu_transformer` package.
They retain the sample timestamp and apply body-axis transformations. The two
callbacks in `imu_node` have distinct inputs/outputs; this is not a feedback loop.
`imu_node` publishes mounting/static TF at initialization, independently of input.
`tf_offset` describes the actual sensor mounting in `base_link`; confirm it on the
boat. Translating the frame does not compensate accelerations for a lever arm.
The near-centre-of-mass assumption is retained.

If orientation is present (`orientation_covariance[0] != -1`), `imu_node` validates
and normalizes the supplied quaternion, preserves it and extracts roll/pitch/yaw.
It does not run the complementary filter or stationary calibration on BNO085
orientation. Existing covariance is retained unless a positive characterized YAML
variance overrides it. Zero configured variance means unknown, not perfect accuracy.
Raw 6-DOF messages with orientation marked absent still use the legacy filter;
`calibration_samples`, `complementary_alpha` and `max_sample_dt_s` apply only there.
The latter limits integration gaps, not the age of a message relative to now.

| Output | Body axes | BNO085 rotation-vector world reference |
| --- | --- | --- |
| `/processed/imu/data` | FLU: forward, left, up | East, magnetic north, up (ENU) |
| `/processed/imu/data/aero` | FRD: forward, right, down | Magnetic north, east, down (NED) |

The configured world rotation is `[180.0, 0.0, 90.0]` degrees. Combined with the
FLU-to-FRD body transform, it maps magnetic ENU to magnetic NED. Robotic yaw is
zero towards east; aero yaw is zero towards magnetic north, increasing towards
east. Declination is not applied, so this is not true north. Aero yaw is unwrapped
across successive samples and can exceed 360 degrees. The conversion changes the
orientation reference, not acceleration/gyro a second time. For the former local
up/down convention use `[180.0, 0.0, 0.0]`; it does not establish a north reference
for raw gyro integration or the BNO085 game rotation vector.

### IMU timing and freshness

```yaml
publish_rate_hz: 0.0
max_sample_age_s: 0.5
```

There is no `read_rate_hz`: subscriptions process new input immediately. Zero
`publish_rate_hz` publishes each new valid result; a positive value periodically
publishes the newest robotic IMU/RPY pair, preserving the acquisition timestamp.
All new inputs are still processed, including when publication is slower. The
aero transformer and callback follow these publications immediately, without a
second timer delay. Repeated input timestamps are not reprocessed, so aero
publication can be lower than the robotic repeat rate when no new sample exists.

`sail_common.freshness.is_fresh` checks each input's original ROS stamp before
processing. Cached periodic results also check elapsed monotonic time, including
with a paused ROS clock. Duplicate and out-of-order samples are ignored. A ROS
clock jump backwards clears the cache, duplicate tracking and estimator/yaw state.
The helper is checked independently on the aero input. No missing or expired
measurement is replaced with a freshly stamped copy. Parameters are read at
startup; rebuild/install and restart after YAML changes.

### Raspberry checks

After deploying the merged setup and rebuilding, verify `/dev/ttyAMA0` and run
one live acquisition/processing stack. Inspect `/imu/data`, `/imu/mag`,
`/processed/imu/rpy` and `/processed/imu/rpy/aero` with `ros2 topic echo` and
measure frequency with `ros2 topic hz`. Check level orientation, known roll/pitch
motions and magnetic heading with the sensor mounted as configured. Stop the
UART stream: acquisition and periodic processed output must expire rather than
repeat indefinitely. Restore it and check reconnection. Offline tests cover
protocol decoding, cache expiry and conversions; physical wiring, calibration,
serial reliability and real ROS scheduling still require this hardware check.

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

Battery acquisition, alarm confirmation and shutdown now all belong to
`sensors/battery_node`. The separate battery monitor and `/processed/battery/low`
output have been removed. Configure `shutdown_enabled`, `low_samples_required`
and `shutdown_command` under `battery_node` in `sensors/config/params.yaml`.
The telemetry gateway continues to subscribe directly to `/battery/data`.
The sensors replay launch explicitly disables shutdown. Rebuild the workspace
with `scripts/build.sh --clean` to remove the old installed node entry point.

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
start five nodes, including both transformer instances, as does replay_data_elaboration.launch.py.
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
  during manoeuvres. Validate BNO085 magnetic heading and declination before
  interpreting it as true north. Use the robotic Imu stream for the future EKF.
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
