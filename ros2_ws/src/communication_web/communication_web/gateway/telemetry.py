"""Build web snapshots without ROS or network dependencies."""

import math


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


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
                 battery_timeout_s, gps_timeout_s):
        self.timeouts = dict(attitude=attitude_timeout_s, height=height_timeout_s,
                             battery=battery_timeout_s, gps=gps_timeout_s)
        self.samples = {}
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
        if not 0 <= now - received <= age_limit:
            return None
        if name != 'battery':
            stamp = message.gps_stamp if name == 'gps' else message.header.stamp
            if not 0 <= now - seconds(stamp) <= age_limit:
                return None
        return message

    def build(self, now):
        self._check_clock(now)
        nan = float('nan')
        telemetry = dict(attitude_valid=False, roll_deg=nan, pitch_deg=nan,
                         yaw_deg=nan, height_valid=False, height_m=nan,
                         battery_valid=False, battery_low=False,
                         sog_valid=False, sog_mps=nan)
        position = dict(fix_valid=False, latitude_deg=nan,
                        longitude_deg=nan, sog_mps=nan)
        attitude = self._fresh('attitude', now)
        if attitude is not None and all(math.isfinite(v) for v in (
                attitude.roll_deg, attitude.pitch_deg, attitude.yaw_deg)):
            telemetry.update(attitude_valid=True, roll_deg=attitude.roll_deg,
                             pitch_deg=attitude.pitch_deg, yaw_deg=attitude.yaw_deg)
        height = self._fresh('height', now)
        if height is not None and math.isfinite(height.height_m):
            telemetry.update(height_valid=True, height_m=height.height_m)
        battery = self._fresh('battery', now)
        if battery is not None:
            telemetry.update(battery_valid=True, battery_low=bool(battery.data))
        gps = self._fresh('gps', now)
        if (gps is not None and gps.fix_valid
                and all(math.isfinite(v) for v in (
                    gps.latitude_deg, gps.longitude_deg, gps.sog_mps))
                and -90 <= gps.latitude_deg <= 90
                and -180 <= gps.longitude_deg <= 180 and gps.sog_mps >= 0):
            telemetry.update(sog_valid=True, sog_mps=gps.sog_mps)
            position.update(fix_valid=True, latitude_deg=gps.latitude_deg,
                            longitude_deg=gps.longitude_deg, sog_mps=gps.sog_mps)
        # Preserve the source timestamp even when a cached fix has expired.
        gps_sample = self.samples.get('gps')
        gps_stamp = gps_sample[0].gps_stamp if gps_sample else None
        return telemetry, position, gps_stamp
