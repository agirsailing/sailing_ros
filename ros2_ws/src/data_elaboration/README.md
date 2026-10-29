# Data elaboration

Consumes ROS sensor messages and publishes derived outputs under /processed/.
No node in this package opens serial, I2C or GPIO devices.

## Topics and messages

| Node | Inputs | Outputs |
| --- | --- | --- |
| ultrasonic_filter_node | /ultrasonic/left, /ultrasonic/right (Range), /processed/imu/data (Imu) | /processed/boat_height (marti_common_msgs/Float64Stamped) |
| imu_mount_transformer_node (imu_transformer) | /imu/data (Imu) | /internal/imu/mounted (Imu, boat-aligned axes) |
| imu_node | /internal/imu/mounted and /internal/imu/aero_body (Imu), handled by separate callbacks | /processed/imu/data and /processed/imu/data/aero (Imu) |
| imu_aero_transformer_node (imu_transformer) | /processed/imu/data (Imu) | /internal/imu/aero_body (Imu, FRD body axes) |

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
reference_frame_id identifies O in Float64Stamped.header; the height node does not publish
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

Each new usable range computes a result, optionally paired with the other side
when the measurement timestamps differ by no more than max_pair_dt_s and both
are fresh. Each candidate retains its own attitude correction.

    w_i = c_i ** incidence_weight_power
    h = sum(w_i h_i) / sum(w_i)

At level attitude the symmetric beams have equal weights. Heeling smoothly
favours the more vertical beam. A single valid sensor is sufficient. A missing
echo need not be an infinite distance; if acquisition stops publishing valid
returns, the old candidate ages out. Invalid new returns clear that side's
candidate immediately. If both sensors stop, cached height expires and publication stops.

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

## Height publication and message

`publish_rate_hz: 20.0` publishes the latest fresh estimate every 50 ms.
Reception remains callback-driven: new range timestamps trigger computation;
IMU callbacks only update the attitude history. The timer does not rerun fusion.
Set `publish_rate_hz: 0.0` to publish each new usable result instead. Negative or
non-finite values are rejected. Change YAML and restart the node to change mode.

`/processed/boat_height` uses `marti_common_msgs/msg/Float64Stamped`:

- `header.stamp`: original triggering range timestamp, unchanged on repeats.
- `header.frame_id`: configured boat waterline reference; no TF is created.
- `value`: signed world-vertical height in metres, positive above the local water
  plane and negative below. This is not distance along body Z.

The shared freshness helper checks every range candidate used in the cached
calculation against `max_range_age_s` (0.5 s), as well as monotonic elapsed time
since calculation. This prevents timer repeats from keeping old measurements alive.
The paired sample can predate the output stamp by up to `max_pair_dt_s`.
An invalid new range clears a cached result that depended on that sensor; a fresh
single-sensor result from the other side remains usable. Invalid attitude, an
unresolved fusion conflict or a backwards clock jump clears the cached result.
No output is published before the first usable estimate or after expiry.

The community ROS package [marti_common_msgs](https://index.ros.org/p/marti_common_msgs/)
provides this stamped scalar in Jazzy. It replaces `sail_msgs/BoatHeight`; the
web gateway translates `value` into the existing dashboard `height_m` field.
ROS/MQTT web payloads are unchanged. Rebuild the Docker image (both Dockerfiles
install `ros-${ROS_DISTRO}-marti-common-msgs`) and run `bash scripts/build.sh --clean`
inside `ros2_ws` to remove the old generated interface. Update external ROS
subscribers to the new type and field; old BoatHeight bags need conversion.

## IMU attitude, mounting and standards

The UART BNO085 now publishes acceleration (m/s^2, including gravity), angular
velocity (rad/s) and onboard fused orientation on `/imu/data`. The sensor's
`rotation_vector` uses its internal accelerometer, gyro and magnetometer; the
separate compass is not fed into this firmware fusion.

The existing mounting pipeline is preserved:

    /imu/data -> imu_mount_transformer_node -> /internal/imu/mounted
      -> imu_node -> /processed/imu/data
      -> imu_aero_transformer_node -> /internal/imu/aero_body
      -> imu_node aero callback -> /processed/imu/data/aero

Both transformers are instances of the external ROS `imu_transformer` package.
They retain the sample timestamp and apply body-axis transformations. The two
callbacks in `imu_node` have distinct inputs/outputs; this is not a feedback loop.
`imu_node` publishes mounting/static TF at initialization, independently of input.
`tf_offset` describes the actual sensor mounting in `base_link`; confirm it on the
boat. Translating the frame does not compensate accelerations for a lever arm.
The near-centre-of-mass assumption is retained.

If orientation is present (`orientation_covariance[0] != -1`), `imu_node` validates
and normalizes the supplied quaternion, preserves it. The web gateway extracts roll/pitch/yaw when building the dashboard.
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
east. Declination is not applied, so this is not true north. Both outputs retain
quaternions; there is no accumulated yaw angle. The gateway represents aero yaw
in [0, 360) degrees, while a conventional robotic Euler extraction uses yaw
counterclockwise from east (usually [-pi, pi] radians). The conversion changes the
orientation reference, not acceleration/gyro a second time. For the former local
up/down convention use `[180.0, 0.0, 0.0]`; it does not establish a north reference
for raw gyro integration or the BNO085 game rotation vector.

### IMU timing and freshness

```yaml
publish_rate_hz: 50.0
max_sample_age_s: 0.5
```

The configured publication target is 50 Hz (one tick every 20 ms), provided
the cached result is still fresh. There is no `read_rate_hz`: subscriptions
process new input immediately. Zero
`publish_rate_hz` publishes each new valid result; a positive value periodically
publishes the newest robotic Imu message, preserving the acquisition timestamp.
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
`/processed/imu/data` and `/processed/imu/data/aero` with `ros2 topic echo` and
measure frequency with `ros2 topic hz`. Check level orientation, known roll/pitch
motions and magnetic heading with the sensor mounted as configured. Stop the
UART stream: acquisition and periodic processed output must expire rather than
repeat indefinitely. Restore it and check reconnection. Offline tests cover
protocol decoding, cache expiry and conversions; physical wiring, calibration,
serial reliability and real ROS scheduling still require this hardware check.

## GPS and navigation

The telemetry gateway subscribes directly to `/gps/data` (`gps_msgs/msg/GPSFix`)
and `/processed/imu/data/aero`. GPS `speed` is SOG in m/s and `track` is course
over ground in degrees. IMU yaw describes orientation, not direction of travel.
There is no speed-based switch between GPS course and a separate compass.
With BNO085 `rotation_vector`, aero yaw references magnetic north, increases
clockwise and is displayed in [0, 360) degrees; calibration and mounting must be verified.

`heading_node`, `GpsSummary`, `/processed/heading_deg` and
`/processed/gps/summary` have been removed. The gateway validates GPS status,
coordinates, speed and the source header using its own `gps_timeout_s` setting.
Dashboard/map ROS and MQTT payloads are unchanged; GPS course remains available
in GPSFix, not in the current web messages. The separate I2C compass acquisition
is still available for diagnostics/recording but is no longer a navigation input.

Run `bash scripts/build.sh --clean` inside the container to remove the obsolete
installed executable and generated message. Update any custom launches and
external subscribers that used the removed interfaces. Old summary-only bags
cannot feed the new gateway; it needs `/gps/data` with the GPSFix type.

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
start four nodes, including both transformer instances, as does replay_data_elaboration.launch.py.
The sensors replay launch still accesses hardware until that pipeline is
implemented. Rebuild sail_msgs and the workspace before using new interfaces.

## TODO / work to revisit

- Navigation references: validate IMU calibration, mounting and magnetic
  declination before comparing bow heading with GPS course over ground.
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

The former `RollPitchYaw` interface and both RPY topics are removed. The gateway
converts the standard aero Imu quaternion to dashboard degrees. Clean-build to
remove the old generated message and update any external subscribers or RPY-only
bag playback. IMU mounting, transforms, freshness and publication rates are unchanged.
