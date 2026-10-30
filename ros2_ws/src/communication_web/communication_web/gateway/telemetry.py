"""Build web snapshots without ROS or network dependencies."""

import math
from sail_common.freshness import is_fresh
from communication_web.gateway.orientation import dashboard_angles


def json_safe(value):
    """Represent unavailable floating-point data as standard JSON null."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class TelemetrySnapshot:
    def __init__(self, attitude_timeout_s, height_timeout_s,
                 battery_timeout_s, gps_timeout_s, ultrasonic_timeout_s=0.5):
        self.timeouts = dict(attitude=attitude_timeout_s, height=height_timeout_s,
                             battery=battery_timeout_s, gps=gps_timeout_s)
        self.samples = {}
        self.timeouts.update(ultrasonic_left=ultrasonic_timeout_s,
                             ultrasonic_right=ultrasonic_timeout_s)
        self.last_time = None

    def _check_clock(self, now):
        # Prevent old samples becoming fresh again after a replay clock reset.
        if self.last_time is not None and now < self.last_time:
            self.samples.clear()
        self.last_time = now

    def update(self, name, message, now):
        self._check_clock(now)
        self.samples[name] = (message, now)

    def _fresh(self, name, now):
        sample = self.samples.get(name)
        if sample is None:
            return None
        message, received = sample
        age_limit = self.timeouts[name]
        # Periodic repeats must retain their source acquisition timestamp.
        if (is_fresh(received, now, age_limit)
                and is_fresh(message.header.stamp, now, age_limit)):
            return message
        return None

    def gps_position(self, now):
        """Return a fresh valid geographical fix; speed is not required."""
        self._check_clock(now)
        gps = self._fresh('gps', now)
        if (gps is not None and gps.status.status >= 0
                and math.isfinite(gps.latitude) and math.isfinite(gps.longitude)
                and -90 <= gps.latitude <= 90 and -180 <= gps.longitude <= 180):
            return gps
        return None

    def build(self, now):
        self._check_clock(now)
        nan = float('nan')
        telemetry = dict(attitude_valid=False, roll_deg=nan, pitch_deg=nan,
                         yaw_deg=nan, height_valid=False, height_m=nan,
                         battery_valid=False, battery_low=False, battery_voltage_v=nan,
                         sog_valid=False, sog_mps=nan)
        position = dict(fix_valid=False, latitude_deg=nan,
                        longitude_deg=nan, sog_mps=nan)
        for side in ('left', 'right'):
            name = 'ultrasonic_' + side
            reading = self._fresh(name, now)
            valid = (reading is not None and all(math.isfinite(v) for v in (
                reading.range, reading.min_range, reading.max_range))
                and 0 <= reading.min_range < reading.max_range
                and reading.min_range <= reading.range <= reading.max_range)
            telemetry[name + '_valid'] = valid
            telemetry[name + '_m'] = reading.range if valid else nan
        attitude = self._fresh('attitude', now)
        angles = dashboard_angles(attitude) if attitude is not None else None
        if angles is not None:
            telemetry.update(attitude_valid=True, roll_deg=angles[0],
                             pitch_deg=angles[1], yaw_deg=angles[2])
        height = self._fresh('height', now)
        if height is not None and math.isfinite(height.value):
            telemetry.update(height_valid=True, height_m=height.value)
        battery = self._fresh('battery', now)
        if battery is not None:
            telemetry.update(battery_valid=True, battery_low=bool(battery.low),
                             battery_voltage_v=battery.voltage_v
                             if math.isfinite(battery.voltage_v) else nan)
        gps = self._fresh('gps', now)
        # GPSStatus.STATUS_FIX is 0; STATUS_NO_FIX is -1. Other valid fixes
        # (e.g. differential/RTK) have positive status codes.
        if (gps is not None and gps.status.status >= 0
                and all(math.isfinite(v) for v in (
                    gps.latitude, gps.longitude, gps.speed))
                and -90 <= gps.latitude <= 90
                and -180 <= gps.longitude <= 180 and gps.speed >= 0):
            telemetry.update(sog_valid=True, sog_mps=gps.speed)
            position.update(fix_valid=True, latitude_deg=gps.latitude,
                            longitude_deg=gps.longitude, sog_mps=gps.speed)
        # Preserve the source timestamp even when a cached fix has expired.
        gps_sample = self.samples.get('gps')
        gps_stamp = gps_sample[0].header.stamp if gps_sample else None
        return telemetry, position, gps_stamp
