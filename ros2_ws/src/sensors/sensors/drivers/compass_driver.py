"""Read signed magnetometer counts using the existing board protocol.

The exact magnetometer model/sensitivity still needs hardware confirmation;
counts are deliberately not labelled as tesla.
"""

import struct
import time

# Register addresses are protocol definitions, not deployment configuration.
DATA_X_L = 0x03
CONTROL_1 = 0x0A
CONTROL_2 = 0x0B


class CompassDriver:
    def __init__(self, mux, channel, address, reset_value, measurement_value,
                 reset_delay_s, conversion_delay_s):
        self.mux, self.channel, self.address = mux, channel, address
        self.measurement_value = measurement_value
        self.conversion_delay_s = conversion_delay_s
        with mux.channel(channel) as bus:
            bus.write_byte_data(address, CONTROL_2, reset_value)
            time.sleep(reset_delay_s)

    def read(self):
        with self.mux.channel(self.channel) as bus:
            bus.write_byte_data(self.address, CONTROL_1, self.measurement_value)
            time.sleep(self.conversion_delay_s)
            data = bus.read_i2c_block_data(self.address, DATA_X_L, 6)
        return struct.unpack('<hhh', bytes(data))
