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
- `communication_web/gateway/telemetry.py`: checks source and receipt times for
  left/right ultrasound, derived height and original GPS data on each dashboard
  tick. GPS freshness uses `gps_stamp`, not the aggregate header timestamp.
- `sensors/gps_node.py`: checks source ROS time and elapsed monotonic time before
  publishing cached NAV-PVT data, independently of `fix_valid`.
- `sensors/battery_node.py`: checks the cached GPIO alarm using source ROS time
  and elapsed monotonic time before publication. Voltage uses its independent
  driver timestamp and age limit; expired voltage becomes NaN without suppressing
  a fresh alarm. Shutdown checks run on new GPIO reads, not republications.
- `sensors/i2c_sensors_node.py`: checks source ROS time and elapsed monotonic time
  independently for IMU and compass snapshots before each publication. Existing
  drivers and conversion delays are unchanged; no downstream migration is part
  of this I2C acquisition step.
- `data_elaboration/heading_node.py` and `processing/heading.py`: check the GPS
  input before summarizing position or using course over ground. Compass and
  other telemetry fields retain existing checks until their migration step.

Limits remain in the owning package's YAML. There is no duplicate global rates
or timeout file. Consumers declare an `exec_depend` on `sail_common`.
