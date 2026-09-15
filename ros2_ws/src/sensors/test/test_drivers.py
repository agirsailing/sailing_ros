"""Offline protocol regression tests; no serial/I2C devices are opened."""

import importlib.util
import math
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sensors.drivers.i2c_mux import I2CMultiplexer
from sensors.drivers.imu_driver import ImuDriver
from sensors.drivers.gps_driver import nav_pvt_values


class DriverTests(unittest.TestCase):
    def test_mux_deselects_on_read_failure(self):
        bus = Mock()
        mux = I2CMultiplexer(bus, 0x70, 4)
        with self.assertRaises(OSError):
            with mux.channel(2):
                raise OSError('read failed')
        self.assertEqual(bus.write_byte.call_args_list[0].args, (0x70, 4))
        self.assertEqual(bus.write_byte.call_args_list[-1].args, (0x70, 0))
        # The failed transaction releases the lock and another channel works.
        with mux.channel(0):
            pass
        self.assertEqual(bus.write_byte.call_args_list[-2].args, (0x70, 1))

    def test_invalid_channel_never_touches_bus(self):
        bus = Mock()
        with self.assertRaises(ValueError):
            with I2CMultiplexer(bus, 0x70, 4).channel(4):
                pass
        bus.write_byte.assert_not_called()

    def test_imu_registers_match_units_and_signed_samples(self):
        bus = Mock()
        mux = I2CMultiplexer(bus, 0x70, 4)
        driver = ImuDriver(mux, 2, 0x6A, 104.0, 4, 500)
        bus.write_byte_data.assert_any_call(0x6A, 0x10, 0x48)
        bus.write_byte_data.assert_any_call(0x6A, 0x11, 0x44)
        bus.read_i2c_block_data.side_effect = [
            list(struct.pack('<hhh', -1000, 0, 1000)),
            list(struct.pack('<hhh', -1000, 0, 1000))]
        accel, gyro = driver.read()
        self.assertAlmostEqual(accel[0], -1.1964113)
        self.assertAlmostEqual(gyro[2], math.radians(17.5))

    def test_gps_does_not_rescale_pyubx_angles_or_dop(self):
        packet = SimpleNamespace(lat=59.0, lon=18.0, hMSL=12340, gSpeed=1500,
                                 headMot=123.45, pDOP=1.25, hAcc=500, vAcc=800,
                                 numSV=12, fixType=3, gnssFixOk=1)
        values = nav_pvt_values(packet)
        self.assertEqual(values['course_deg'], 123.45)
        self.assertEqual(values['position_dop'], 1.25)
        self.assertEqual(values['ground_speed_mps'], 1.5)
        self.assertTrue(values['fix_valid'])
        packet.gnssFixOk = 0
        self.assertFalse(nav_pvt_values(packet)['fix_valid'])

    def test_ultrasonic_partial_corrupt_and_stale_frames(self):
        stream = Mock()
        stream.in_waiting = 0
        path = Path(__file__).resolve().parents[1] / 'sensors/drivers/ultrasonic_driver.py'
        spec = importlib.util.spec_from_file_location('tested_ultrasonic_driver', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'serial': SimpleNamespace(Serial=Mock(return_value=stream))}):
            spec.loader.exec_module(module)
        driver = module.DFRobot_A02_Distance('test', 9600, 0.1)
        driver.set_dis_range(0, 4500)
        good = bytes([255, 3, 232, (255 + 3 + 232) & 255])
        stream.read.side_effect = [good[:2], good[2:], b'', b'\xff\x03\xe8\x00' + good]
        self.assertIsNone(driver.getDistance())
        self.assertEqual(driver.getDistance(), 1000)
        self.assertEqual(driver.last_operate_status, driver.STA_OK)
        self.assertIsNone(driver.getDistance())
        self.assertNotEqual(driver.last_operate_status, driver.STA_OK)
        self.assertEqual(driver.getDistance(), 1000)
        driver.close()
        stream.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
