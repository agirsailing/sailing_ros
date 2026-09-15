"""LSM6DS3TR-C acquisition; no bias correction or orientation estimation."""

import math
import struct

CTRL1_XL = 0x10
CTRL2_G = 0x11
CTRL3_C = 0x12
OUTX_L_G = 0x22
OUTX_L_XL = 0x28

# Datasheet encodings and sensitivities are fixed by the hardware protocol.
ODR_BITS = {12.5: 1, 26.0: 2, 52.0: 3, 104.0: 4, 208.0: 5,
            416.0: 6, 833.0: 7, 1660.0: 8}
ACCEL_RANGES = {2: (0, 0.061), 4: (2, 0.122),
                8: (3, 0.244), 16: (1, 0.488)}
GYRO_RANGES = {125: (2, 4.375), 250: (0, 8.75), 500: (4, 17.5),
               1000: (8, 35.0), 2000: (12, 70.0)}


class ImuDriver:
    def __init__(self, mux, channel, address, odr_hz, accel_range_g,
                 gyro_range_dps):
        self.mux, self.channel, self.address = mux, channel, address
        odr = ODR_BITS[odr_hz] << 4
        accel_bits, accel_mg = ACCEL_RANGES[accel_range_g]
        gyro_bits, gyro_mdps = GYRO_RANGES[gyro_range_dps]
        self.accel_scale = accel_mg * 1e-3 * 9.80665
        self.gyro_scale = math.radians(gyro_mdps * 1e-3)
        with mux.channel(channel) as bus:
            # Block data update and register auto-increment for coherent reads.
            bus.write_byte_data(address, CTRL3_C, 0x44)
            bus.write_byte_data(address, CTRL1_XL, odr | (accel_bits << 2))
            bus.write_byte_data(address, CTRL2_G, odr | gyro_bits)

    def read(self):
        with self.mux.channel(self.channel) as bus:
            gyro = bus.read_i2c_block_data(self.address, OUTX_L_G, 6)
            accel = bus.read_i2c_block_data(self.address, OUTX_L_XL, 6)
        acceleration = tuple(v * self.accel_scale for v in struct.unpack('<hhh', bytes(accel)))
        angular_velocity = tuple(v * self.gyro_scale for v in struct.unpack('<hhh', bytes(gyro)))
        return acceleration, angular_velocity
