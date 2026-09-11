import csv
import fcntl
import math
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import rclpy
import smbus2
from geometry_msgs.msg import Quaternion
from rclpy.node import Node
from sensor_msgs.msg import Imu

MUX_ADDR    = 0x70
MUX_CHANNEL = 1          # write (1 << 1) = 0x02 to enable SC2/SD2

IMU_ADDR  = 0x6A
CTRL1_XL  = 0x10         # accelerometer control
CTRL2_G   = 0x11         # gyroscope control
OUTX_L_G  = 0x22         # first of 6 gyro output bytes
OUTX_L_XL = 0x28         # first of 6 accel output bytes

# Sensitivity at ODR = 104 Hz, ±4 g / ±500 dps
ACCEL_SENS = 0.122e-3 * 9.80665        # m/s² per LSB
GYRO_SENS  = 17.50e-3 * (math.pi / 180.0)  # rad/s per LSB

CALIB_SAMPLES = 200   # ~2 s at 100 Hz — keep sensor perfectly still

# Shared lock so this node and the GPS/compass node don't race on the bus
I2C_LOCK_PATH = "/tmp/i2c_bus1.lock"

def _signed16(hi: int, lo: int) -> int:
    """Combine two bytes into a signed 16-bit integer (little-endian)."""
    val = (hi << 8) | lo
    return val - 65536 if val >= 32768 else val


@contextmanager
def _bus_lock():
    """Exclusive cross-process lock around a single I2C transaction block."""
    with open(I2C_LOCK_PATH, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _rpy_to_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    """
    Roll/pitch/yaw (radians) → unit quaternion using ZYX intrinsic convention.
    ROS uses quaternions to avoid gimbal lock and for smooth interpolation.
    """
    cr, sr = math.cos(roll  / 2), math.sin(roll  / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw   / 2), math.sin(yaw   / 2)

    q = Quaternion()
    q.w = cr * cp * cy + sr * sp * sy
    q.x = sr * cp * cy - cr * sp * sy
    q.y = cr * sp * cy + sr * cp * sy
    q.z = cr * cp * sy - sr * sp * cy
    return q

class ImuNode(Node):

    def __init__(self):
        super().__init__("imu_node")

        # ROS parameters
        self.declare_parameter("i2c_bus",   1)
        self.declare_parameter("topic",     "imu/data_raw")
        self.declare_parameter("device_id", "imu")
        self.declare_parameter("rate_hz",   50.0)

        bus_num        = self.get_parameter("i2c_bus").get_parameter_value().integer_value
        topic          = self.get_parameter("topic").get_parameter_value().string_value
        self.device_id = self.get_parameter("device_id").get_parameter_value().string_value
        rate_hz        = self.get_parameter("rate_hz").get_parameter_value().double_value

        # I2C bus
        self.bus = smbus2.SMBus(bus_num)
        self._init_imu()

        # Calibration — sensor must be perfectly still
        self.get_logger().info(f"{self.device_id}: calibrating — keep sensor still…")
        (self.ax_off, self.ay_off, self.az_off,
         self.gx_off, self.gy_off, self.gz_off) = self._calibrate()
        self.get_logger().info(
            f"{self.device_id}: calibration done | "
            f"gyro offsets (rad/s)  gx={self.gx_off:.4f}  "
            f"gy={self.gy_off:.4f}  gz={self.gz_off:.4f}"
        )

        # Complementary filter state
        self.roll  = 0.0
        self.pitch = 0.0
        self.yaw   = 0.0
        self.dt    = 1.0 / rate_hz
        self.alpha = 0.98   # 98 % gyro, 2 % accelerometer

        # CSV log
        self.csv_path = self._init_csv()

        # ROS publisher + timer
        self.pub   = self.create_publisher(Imu, topic, 10)
        self.timer = self.create_timer(self.dt, self._timer_cb)

        self.get_logger().info(
            f"{self.device_id}: publishing '{topic}' @ {rate_hz} Hz | "
            f"CSV → {self.csv_path}"
        )

    def destroy_node(self):
        self.bus.close()
        super().destroy_node()

    def _init_imu(self):
        """Configure accelerometer (104 Hz, ±4 g) and gyroscope (104 Hz, ±500 dps)."""
        with _bus_lock():
            self._mux_select()
            self.bus.write_byte_data(IMU_ADDR, CTRL1_XL, 0x48)  # ODR=104Hz ±4g
            self.bus.write_byte_data(IMU_ADDR, CTRL2_G,  0x54)  # ODR=104Hz ±500dps
            self._mux_deselect()

    def _mux_select(self):
        """Enable IMU channel on PCA9546 — call inside _bus_lock()."""
        self.bus.write_byte(MUX_ADDR, 1 << MUX_CHANNEL)

    def _mux_deselect(self):
        """Disable all PCA9546 channels — call inside _bus_lock()."""
        self.bus.write_byte(MUX_ADDR, 0x00)

    def _read_raw(self) -> tuple[float, float, float, float, float, float]:
        """Read scaled accel (m/s²) and gyro (rad/s) — call inside _bus_lock()."""
        raw_g  = self.bus.read_i2c_block_data(IMU_ADDR, OUTX_L_G,  6)
        raw_xl = self.bus.read_i2c_block_data(IMU_ADDR, OUTX_L_XL, 6)

        gx = _signed16(raw_g[1],  raw_g[0])  * GYRO_SENS
        gy = _signed16(raw_g[3],  raw_g[2])  * GYRO_SENS
        gz = _signed16(raw_g[5],  raw_g[4])  * GYRO_SENS

        ax = _signed16(raw_xl[1], raw_xl[0]) * ACCEL_SENS
        ay = _signed16(raw_xl[3], raw_xl[2]) * ACCEL_SENS
        az = _signed16(raw_xl[5], raw_xl[4]) * ACCEL_SENS

        return ax, ay, az, gx, gy, gz

    def _calibrate(self) -> tuple[float, ...]:
        """
        Average CALIB_SAMPLES readings to find static offsets.
        Subtracting offsets makes a still sensor read (0,0,9.81) accel
        and (0,0,0) gyro — so roll = pitch = yaw = 0 at boot pose.
        """
        sums = [0.0] * 6

        with _bus_lock():
            self._mux_select()
            for _ in range(CALIB_SAMPLES):
                for i, v in enumerate(self._read_raw()):
                    sums[i] += v
            self._mux_deselect()

        n = CALIB_SAMPLES
        ax_off = sums[0] / n
        ay_off = sums[1] / n
        az_off = sums[2] / n - 9.80665   # remove static offset, keep gravity
        gx_off = sums[3] / n
        gy_off = sums[4] / n
        gz_off = sums[5] / n

        return ax_off, ay_off, az_off, gx_off, gy_off, gz_off

    def _read_imu(self) -> tuple[float, float, float, float, float, float]:
        """Read raw values and subtract calibration offsets — call inside _bus_lock()."""
        ax, ay, az, gx, gy, gz = self._read_raw()
        return (
            ax - self.ax_off,
            ay - self.ay_off,
            az - self.az_off,
            gx - self.gx_off,
            gy - self.gy_off,
            gz - self.gz_off,
        )

    def _update_angles(self, ax, ay, az, gx, gy, gz):
        accel_roll  = math.atan2(ay, az)
        accel_pitch = math.atan2(-ax, math.sqrt(ay**2 + az**2))

        self.roll  = self.alpha * (self.roll  + gx * self.dt) + (1.0 - self.alpha) * accel_roll
        self.pitch = self.alpha * (self.pitch + gy * self.dt) + (1.0 - self.alpha) * accel_pitch
        self.yaw  += gz * self.dt   # gyro-only; fuse magnetometer here when ready

    def _init_csv(self) -> str:
        log_dir = os.path.expanduser("~/ros2_ws/CSVs")
        os.makedirs(log_dir, exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(log_dir, f"imu_{self.device_id}_{ts}.csv")
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow([
                "timestamp_utc", "device_id",
                "roll_deg", "pitch_deg", "yaw_deg",
                "ax_mps2", "ay_mps2", "az_mps2",
                "gx_rads", "gy_rads", "gz_rads",
            ])
        return path

    def _write_csv(self, utc, ax, ay, az, gx, gy, gz, roll_deg, pitch_deg, yaw_deg):
        try:
            with open(self.csv_path, "a", newline="") as f:
                csv.writer(f).writerow([
                    utc, self.device_id,
                    round(roll_deg,  4),
                    round(pitch_deg, 4),
                    round(yaw_deg,   4),
                    round(ax, 6), round(ay, 6), round(az, 6),
                    round(gx, 6), round(gy, 6), round(gz, 6),
                ])
        except OSError as e:
            self.get_logger().error(f"CSV write failed: {e}")

    def _timer_cb(self):
        # Read sensor (bus lock held only for the I2C transaction)
        try:
            with _bus_lock():
                self._mux_select()
                ax, ay, az, gx, gy, gz = self._read_imu()
                self._mux_deselect()
        except OSError as e:
            self.get_logger().error(f"{self.device_id}: I2C read failed — {e}")
            return

        # Update orientation filter
        self._update_angles(ax, ay, az, gx, gy, gz)

        roll_deg  = math.degrees(self.roll)
        pitch_deg = math.degrees(self.pitch)
        yaw_deg   = math.degrees(self.yaw)

        # Build and publish ROS message
        msg                    = Imu()
        msg.header.stamp       = self.get_clock().now().to_msg()
        msg.header.frame_id    = self.device_id
        msg.angular_velocity.x = gx
        msg.angular_velocity.y = gy
        msg.angular_velocity.z = gz
        msg.linear_acceleration.x = ax
        msg.linear_acceleration.y = ay
        msg.linear_acceleration.z = az
        msg.orientation = _rpy_to_quaternion(self.roll, self.pitch, self.yaw)

        # -1.0 in [0] = "covariance unknown" per ROS convention.
        # Replace with real noise values once you characterise the sensor.
        msg.orientation_covariance[0]         = -1.0
        msg.angular_velocity_covariance[0]    = -1.0
        msg.linear_acceleration_covariance[0] = -1.0

        self.pub.publish(msg)

        self.get_logger().info(
            f"{self.device_id}:  "
            f"roll={roll_deg:+7.2f}°  pitch={pitch_deg:+7.2f}°  yaw={yaw_deg:+7.2f}°"
        )

        # Log to CSV (outside the bus lock — pure file I/O)
        utc = datetime.now(timezone.utc).isoformat()
        self._write_csv(utc, ax, ay, az, gx, gy, gz, roll_deg, pitch_deg, yaw_deg)

def main(args=None):
    rclpy.init(args=args)
    node = ImuNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()