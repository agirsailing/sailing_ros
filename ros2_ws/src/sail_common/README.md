# sail_common

Shared Python utilities, installed as an `ament_python` package. This package
contains no nodes, timers, hardware configuration or message definitions.

## Freshness

```python
from sail_common.freshness import is_fresh

usable = is_fresh(msg.header.stamp, node.get_clock().now(), max_age_s)
```

The single policy is `0 <= now - stamp <= max_age_s`, with an inclusive expiry
boundary and a finite, positive limit in seconds. The helper accepts ROS
`builtin_interfaces/Time`, `rclpy.time.Time`, or numeric seconds. Passing a bare
`msg.stamp` works too. Integer ROS timestamps retain nanosecond precision.
Missing, malformed, non-finite and future timestamps return false. Invalid
limits raise `ValueError`. Time zero is valid during simulation; use `None` or
an absent cached sample to represent "nothing received yet".

Inputs MUST share a clock and epoch. Clock identity is not carried in ROS Time
messages; the caller must choose the correct clock and synchronize machines.
Known clock-type mismatches between two `rclpy.time.Time` objects are rejected.
Numeric arguments are seconds, never raw integer nanoseconds.

Call at reception and again before consuming cached measurements. The function
does not schedule callbacks, mutate caches, check physical validity, or guarantee
the presence of a publisher. Time going backwards makes future samples stale;
owners of histories must also clear them when a clock reset occurs, so an old
sample cannot become usable again when the clock catches up.

Migration is incremental. Current users:

- `sensors/ultrasonic_node.py`: checks source ROS time and, separately, elapsed
  monotonic time before each publication. The latter expires data even when ROS
  time is paused. The two clock domains are never compared with each other.
- `data_elaboration/ultrasonic_filter_node.py`: checks incoming ranges, attitude
  history eligibility and candidates before height fusion. Clock-reset cleanup
  and duplicate rejection remain local to the estimator.
- `communication_web/telemetry_gateway_node.py`: checks recording-state receipt
  age before each MQTT state tick (no source header is available in RecordingState).
- `communication_web/gateway/telemetry.py`: checks source and receipt times for
  every input on each dashboard tick, including processed attitude, height,
  battery, ultrasound and GPSFix received directly from `/gps/data`.
  GPS freshness uses its original header, copied to `MapDataMsg.gps_stamp`.
- `sensors/gps_node.py`: checks source ROS time and elapsed monotonic time before
  publishing cached NAV-PVT data, independently of `fix_valid`.
- `sensors/battery_node.py`: checks the cached GPIO alarm using source ROS time
  and elapsed monotonic time before publication. Voltage uses its independent
  driver timestamp and age limit; expired voltage becomes NaN without suppressing
  a fresh alarm. Shutdown checks run on new GPIO reads, not republications.
- `sensors/i2c_sensors_node.py`: checks source ROS time and elapsed monotonic time
  for compass snapshots before each publication. Its conversion delay is unchanged.
- `sensors/imu_sensor_node.py` and `drivers/imu_driver.py`: check each BNO085
  component independently and expire cached UART measurements without renewing
  timestamps on republication.
- `data_elaboration/ultrasonic_filter_node.py`: checks range/attitude alignment
  during computation, then rechecks source ages and elapsed monotonic time before
  publishing a cached Float64Stamped height. Repeats never renew source stamps.
- `data_elaboration/imu_node.py`: accepts fresh mounted/aero input, rejects repeated
  timestamps and expires periodic robotic output using source and receipt times.

Limits remain in the owning package's YAML. There is no duplicate global rates
or timeout file. Consumers declare an `exec_depend` on `sail_common`.
