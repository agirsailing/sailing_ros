"""DFRobot A02YYUW serial distance driver.

Derived from DFRobot_RaspberryPi_A02YYUW.py, version 1.0 (2021-08-30).
Copyright (c) 2010 DFRobot Co.Ltd (http://www.dfrobot.com)
Author: Arya (xue.peng@dfrobot.com)
License: MIT
https://github.com/DFRobot/DFRobot_RaspberryPi_A02YYUW

Serial framing and checksums are hardware protocol constants.
"""

import serial


class DFRobot_A02_Distance:
    STA_OK = 0x00
    STA_ERR_CHECKSUM = 0x01
    STA_ERR_SERIAL = 0x02
    STA_ERR_CHECK_OUT_LIMIT = 0x03
    STA_ERR_CHECK_LOW_LIMIT = 0x04
    STA_ERR_DATA = 0x05

    def __init__(self, port, baudrate, timeout):
        self._ser = serial.Serial(port, baudrate, timeout=timeout)
        self._buffer = bytearray()
        self.last_operate_status = self.STA_ERR_DATA
        self.distance = None
        self.minimum = None
        self.maximum = None

    def set_dis_range(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum

    def getDistance(self):
        if self.minimum is None:
            raise ValueError('Configure the measurement range before reading')
        # Preserve partial frames across callbacks; limit blocking with the
        # serial timeout and never return an old sample as a successful read.
        self._buffer.extend(self._ser.read(max(1, self._ser.in_waiting)))
        self.last_operate_status = self.STA_ERR_DATA
        while self._buffer:
            if self._buffer[0] != 0xFF:
                del self._buffer[0]
                continue
            if len(self._buffer) < 4:
                break
            frame = self._buffer[:4]
            if (sum(frame[:3]) & 0xFF) != frame[3]:
                self.last_operate_status = self.STA_ERR_CHECKSUM
                del self._buffer[0]
                continue
            del self._buffer[:4]
            self.distance = (frame[1] << 8) | frame[2]
            if self.distance < self.minimum:
                self.last_operate_status = self.STA_ERR_CHECK_LOW_LIMIT
            elif self.distance > self.maximum:
                self.last_operate_status = self.STA_ERR_CHECK_OUT_LIMIT
            else:
                self.last_operate_status = self.STA_OK
            return self.distance
        return None

    def close(self):
        self._ser.close()
