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
        # Non-blocking: take only what has already arrived.
        waiting = self._ser.in_waiting
        if waiting:
            self._buffer.extend(self._ser.read(waiting))

        latest = None
        status = self.STA_ERR_DATA
        # Parse ALL complete frames; keep the newest valid one.
        while len(self._buffer) >= 4:
            if self._buffer[0] != 0xFF:
                del self._buffer[0]
                continue
            frame = self._buffer[:4]
            if (sum(frame[:3]) & 0xFF) != frame[3]:
                status = self.STA_ERR_CHECKSUM
                del self._buffer[0]
                continue
            del self._buffer[:4]
            latest = (frame[1] << 8) | frame[2]
        # Any trailing partial frame (<4 bytes) stays for the next call.

        if latest is None:
            self.last_operate_status = status
            return None
        self.distance = latest
        if latest < self.minimum:
            self.last_operate_status = self.STA_ERR_CHECK_LOW_LIMIT
        elif latest > self.maximum:
            self.last_operate_status = self.STA_ERR_CHECK_OUT_LIMIT
        else:
            self.last_operate_status = self.STA_OK
        return latest

    def close(self):
        self._ser.close()
