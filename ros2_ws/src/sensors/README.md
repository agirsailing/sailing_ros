# Sensors

Nodes acquire hardware measurements. battery_node also owns the low-battery
shutdown policy; calibration, filtering and heading selection belong to data_elaboration.

## Configuration and endpoints

- config/params.yaml: all deployment parameters for nodes in this package.
  Missing parameters fail explicitly; there are no hidden hardware defaults.
- config/endpoints.yaml: the only source for sensor topic names.
- sensors/generated/ros_endpoints.py: generator output imported by publishers
  and by downstream packages. build.sh regenerates it before colcon.
- Register addresses, protocol frames and SI unit conversions remain in drivers:
  they define the protocol rather than the installation configuration.
- The left/right bow sensors select generated endpoint groups from YAML.
  Both are enabled. Set enabled: false for an absent sensor; the height estimator
  can use a single valid sensor. Full Pi setup installs stable udev names tied
  to physical USB ports: left=1.4, right=1.3, GPS=1.2. Keep cables in these ports.
  Beam angles and mounting positions belong
  to data_elaboration/config/params.yaml; acquisition publishes slant ranges.

## Acquisition

| Node | Interface | Message / topic |
| --- | --- | --- |
| ultrasonic_left_node | /dev/ultrasonic_left | sensor_msgs/Range /ultrasonic/left (m) |
| ultrasonic_right_node | /dev/ultrasonic_right | sensor_msgs/Range /ultrasonic/right (m) |
| gps_node | /dev/gps, NAV-PVT | sail_msgs/GpsData /gps/data |
| i2c_sensors_node | bus 1, mux 0x70, channel 2 | sensor_msgs/Imu /imu/data |
| i2c_sensors_node | same mux, channel 0 | geometry_msgs/Vector3Stamped /compass/data |
| battery_node | gpiochip0 line 13 (alarm), line 6 (ESP32 voltage link) | sail_msgs/BatteryData /battery/data |

### Ultrasound reading and publication

Both ultrasound nodes use independent settings in `config/params.yaml`:

```yaml
read_rate_hz: 0.0
publish_rate_hz: 20.0
max_sample_age_s: 0.5
timeout_s: 0.1
```

- `read_rate_hz: 0.0` waits for serial bytes as they arrive in a dedicated reader
  thread, without blocking the ROS executor or busy polling. A positive value,
  such as `10.0`, instead checks buffered serial data at that nominal rate.
  Neither setting changes the physical sensor's measurement rate.
- `publish_rate_hz` sets an independent ROS timer. At 20 Hz it publishes the
  latest usable sample every 50 ms. If several samples arrive between ticks,
  only the newest is published; there is no queue of historical measurements.
- `max_sample_age_s` bounds reuse: no publication occurs before the first valid
  sample or once the latest sample is older than 0.5 s. Invalid measurements and
  serial errors clear the cached sample immediately.
- `timeout_s` bounds an idle serial read. A byte arriving before the timeout
  wakes the reader immediately; 0.1 s does **not** impose a 10 Hz read limit.

The driver checks frame checksums and converts millimetres to metres in the node.
`Range.header.stamp` is set when a complete valid frame is decoded on the host.
The serial protocol has no measurement timestamp, so time spent in the sensor or
serial buffers cannot be reconstructed. Repeated publications preserve this stamp;
a newly received measurement gets a new stamp even when its numeric value is equal.
The height estimator already rejects repeated timestamps. Publishing at 20 Hz
therefore does not imply 20 distinct physical measurements or height updates/s.

Freshness uses `sail_common.freshness.is_fresh` before every publication, checking
both the source ROS timestamp and elapsed monotonic time separately. A paused
ROS clock cannot preserve an expired sample. The same helper is used by the
height estimator and the ultrasound/height fields in the web gateway.

These settings are read at startup. Replace the old ultrasound `rate_hz` entry
with the new parameters in any custom YAML, rebuild/install the package and
restart the nodes. Battery and I2C timing controls are documented below.

### GPS reading and publication

`gps_node` publishes `sail_msgs/GpsData` on `/gps/data`. Its timing is independent
of the ultrasound nodes and configured in the same package YAML:

```yaml
read_rate_hz: 0.0
publish_rate_hz: 10.0
max_sample_age_s: 1.0
timeout_s: 0.1
```

The reader runs outside the ROS executor. Zero `read_rate_hz` waits for incoming
packets continuously; a positive rate drains buffered packets on each poll,
rather than reading only one packet per tick. Partial packets survive serial
timeouts. `timeout_s` bounds each underlying idle read so shutdown can interrupt
the worker; it does not impose a 10 Hz acquisition limit. Serial errors clear the
cached sample and retries back off. An unplugged/re-enumerated port can require
restarting the node; automatic port reopening is not implemented.

Only NAV-PVT packets update the cached measurement. NMEA and other UBX packets
do not refresh its age. An independent timer publishes the latest NAV-PVT at
10 Hz by default, preserving its host decoding timestamp on repeats. It never
queues historical snapshots for later publication. Reading faster does not
configure the receiver's physical measurement or NAV-PVT output frequency.
The stamp is host decoding time, not receiver UTC or a reconstruction of time
spent inside the receiver/serial buffer.

`fix_valid` is preserved: it combines the receiver's `gnssFixOk` flag with the
accepted fix types (2, 3, 4). A new packet with `fix_valid=false` replaces the
previous valid fix and is still published. Freshness and fix quality are separate:
`sail_common.freshness.is_fresh` checks ROS source time and elapsed monotonic time
before publication, even if ROS time is paused. No publication occurs before the
first NAV-PVT or after it exceeds `max_sample_age_s`.

The heading/summary node and the GPS field in the web gateway also use the shared
helper. `GpsSummary.gps_stamp` and `MapDataMsg.gps_stamp` retain the original GPS
timestamp, so refreshed summaries cannot make an old position appear new.
Consumer thresholds remain in their own YAML files. Replace the old GPS
`rate_hz` in custom configs with the three new parameters above, rebuild/install
and restart. These settings are read at startup, not changed live.

### Battery data and shutdown

`battery_node` uses separate ROS timers for GPIO polling and publication:

```yaml
read_rate_hz: 10.0
publish_rate_hz: 10.0
max_sample_age_s: 0.5
voltage_max_age_s: 5.0
```

All four values must be finite and positive. Unlike ultrasound/GPS serial
readers, `read_rate_hz: 0.0` is not supported: the low-alarm GPIO is polled.
ESP32 voltage reception remains callback-driven in the unchanged driver;
`read_rate_hz` does not configure the sender's measurement rate. Each successful
GPIO read caches the alarm, its ROS timestamp, host monotonic time and the latest
voltage tuple. The publication timer reuses only the latest snapshot and preserves
the GPIO timestamp on repeats, without reading hardware or checking shutdown.

Before each publication, `sail_common.freshness.is_fresh` checks both the GPIO
source ROS timestamp and elapsed monotonic time independently. No message is
published before the first successful read or after `max_sample_age_s`, including
when ROS time is paused. Read errors immediately clear the cached snapshot.
Voltage freshness is checked separately against its driver's monotonic timestamp
on every publication using `voltage_max_age_s`. The driver timestamps decoding,
which currently occurs on an edge of the following packet; this does not recover
the original ESP32 measurement time.

BatteryData contains only `header`, `voltage_v` (volts) and `low` (raw GPIO alarm).
`header.stamp` is the ROS time of the GPIO reading; `header.frame_id` stays empty
because these scalars have no spatial frame. Voltage is the latest ESP32 reading,
not necessarily acquired at that timestamp; absent or expired voltage is NaN
(5-second limit by default). A GPIO read failure suppresses the entire snapshot, so consumers must
expire missing messages rather than treating a missing alarm as false.
There are no per-field validity booleans and no charge-percentage estimate.
The separate `/battery/voltage` publisher has been removed.

battery_node also counts consecutive successful `low=true` GPIO reads and, once
the configured threshold is reached, requests shutdown at most once per node
execution. This runs in the read callback, independently of publication; repeated
publications never count as new confirmations. Lowering publication frequency
does not slow alarm checking. A shutdown request does not wait for publication
of the new alarm snapshot.
`BatteryData.low` remains the raw GPIO alarm, not the confirmation result.
In config/params.yaml, `shutdown_enabled` defaults to true,
`low_samples_required` to 1 and `shutdown_command` to `[sudo, shutdown, "-h", now]`.
A valid `low=false` sample clears the counter. Missing voltage does not suppress
a GPIO alarm or the shutdown request. GPIO read errors produce no new sample
and do not advance the counter. A failed shutdown command is logged, without
repeated execution on every sample. Its effect on the host depends on Docker.
There is no separate monitoring node or `/processed/battery/low` topic.

Replace the old battery `rate_hz` entry in custom YAML with the four parameters
above, rebuild/install and restart the node. Settings are read at startup, not
changed live. This refactor does not change downstream nodes or the message fields.

Compass values are signed raw counts, not tesla: the exact model and sensitivity
still need hardware confirmation. IMU acceleration is m/s^2 and gyro is rad/s.
Raw IMU orientation is absent (orientation_covariance[0] = -1); the measured
vectors have zero covariances to indicate unknown uncertainty.

The mux owner holds a lock across channel selection, sensor access and
deselection, including failures. The lock protects only this process; do not
launch another program that manually operates this mux. A failed sensor is
retried independently. Compass conversion currently holds the bus for 20 ms:
the configured 50 Hz IMU rate is nominal and can jitter. Processing uses message
timestamps, not an assumed fixed interval. A kernel mux driver or asynchronous
conversion scheduling may be considered after hardware timing measurements.

### I2C polling and replacement hardware

Each sensor has independent acquisition and publication settings:

```yaml
imu:
  read_rate_hz: 50.0
  publish_rate_hz: 50.0
  max_sample_age_s: 0.5
compass:
  read_rate_hz: 10.0
  publish_rate_hz: 10.0
  max_sample_age_s: 0.5
```

All rates and age limits must be finite and positive. These are startup settings;
zero does not select arrival-driven reading for I2C. Migrate custom YAML from
`imu.rate_hz` / `compass.rate_hz` to the three parameters per sensor, rebuild and
restart. No downstream node is changed by this acquisition refactor.

One polling worker per enabled sensor calls the existing driver. The mux's
existing lock serializes select/read/deselect operations. Separate ROS timers
publish the latest complete snapshot without accessing the bus. Raising
`publish_rate_hz` does not cause additional reads; lowering it keeps only the
newest acquired sample, without queueing historical snapshots. Polling rates are
nominal: the unchanged compass conversion delay can still postpone IMU reads,
but waiting for that conversion does not block the ROS publication callbacks.

Before every publication, `sail_common.freshness.is_fresh` checks the original
host-read ROS timestamp and, separately, elapsed monotonic time. Repeated
publications retain the acquisition stamp. Nothing is published before the first
successful read or after `max_sample_age_s`; a read failure immediately clears
only that sensor's cached sample. Retry deadlines use monotonic time, so ROS clock
pauses do not prevent recovery. Each new successful register read is stamped on
the host; without hardware data-ready handling this does not prove that the
sensor internally produced a different sample. Disabled sensors have no reader
or publisher, and shutdown joins workers before closing the shared bus.

`imu.odr_hz` controls internal measurement generation, not register polling or ROS
publication. The driver currently targets LSM6DS3TR-C (six axes) plus a separate
magnetometer. The replacement board has been identified as Adafruit BNO085;
the driver migration is not yet implemented. The existing 104 Hz setting and
register protocol must not be used as BNO085 configuration.

`compass.conversion_delay_s` remains the wait between the measurement command and
reading the result. Its 20 ms value needs hardware confirmation; removing it
without checking the sensor protocol could read an unfinished or previous result.
Polling frequency and sample freshness do not replace conversion readiness.

The BNO085 has onboard sensor fusion and provides accelerometer, gyroscope,
magnetometer and orientation reports. Adafruit's BNO08x driver requests report
intervals in microseconds (`enable_feature(..., report_interval=...)`): a 20,000 us
request corresponds to 50 reports/s. Requested report frequency, host reads and
ROS publication are distinct; a report interval is not the old LSM6DS3TR-C ODR
register setting. Its magnetometer reports do not use this legacy driver's
per-measurement command/sleep/read sequence. Any separate external compass still
needs its own verified conversion timing.

BNO085 is used as the IMU through the multiplexer, with a separate compass;
the replacement driver and exact hardware routing are being handled separately.
Adafruit explicitly
reports BNO08x I2C compatibility issues with multiplexers; reducing polling rate
alone does not establish reliability. The downstream IMU node currently computes
orientation from acceleration/gyro: adopting BNO085 fused orientation is a
separate processing change, not automatically enabled by changing acquisition.

References for the replacement board:

- [Adafruit BNO085 overview and I2C compatibility note](https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085)
- [Adafruit report configuration implementation](https://github.com/adafruit/Adafruit_CircuitPython_BNO08x/blob/main/adafruit_bno08x/__init__.py)

## Launch

live_sensors.launch.py and replay_sensors.launch.py both start all acquisition
nodes, including IMU via i2c_sensors_node. Replay explicitly overrides
`shutdown_enabled=false` for battery_node after loading the shared YAML.
sensors_launch.py is a compatibility entry point with the same acquisition set.
Replay is not yet a hardware-free bag pipeline. Do not start both modes together.

Both launch files accept sensors_params_file to override the installed YAML.
The orchestrator now includes sensors and data_elaboration for each mode.

## Hardware checks still required

USB enumeration, actual wiring, GPIO permissions, mux model/channel count and
magnetometer register protocol have not been verified on the Raspberry.
No Docker commands or ROS/hardware execution were used during the refactor.

## References

- pyubx2 NAV-PVT field scaling:
  https://github.com/semuconsulting/pyubx2/blob/master/src/pyubx2/ubxtypes_get.py
- LSM6DS3TR-C register settings and sensitivities:
  https://www.st.com/resource/en/datasheet/lsm6ds3tr-c.pdf
- ROS Imu covariance conventions:
  https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/Imu.msg
