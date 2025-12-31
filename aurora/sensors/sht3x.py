"""SHT3x ambient temperature and humidity reader with CRC check."""

import struct
import time
from typing import Optional, Tuple

import aurora.config as config

CRC_POLY = 0x31
CRC_INIT = 0xFF


def _crc8(data):
    crc = CRC_INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ CRC_POLY
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


class SHT3x:
    def __init__(self, address=None):
        self.address = address

    def _read_raw(self):
        # Placeholder: MicroPython should write command then read 6 bytes
        return None

    def read(self) -> Tuple[Optional[float], Optional[float]]:
        raw = self._read_raw()
        if raw is None or len(raw) != 6:
            return None, None
        if raw[2] != _crc8(raw[0:2]) or raw[5] != _crc8(raw[3:5]):
            return None, None
        temp_raw = raw[0] << 8 | raw[1]
        rh_raw = raw[3] << 8 | raw[4]
        temperature = -45 + (175 * temp_raw / 65535.0)
        humidity = 100 * rh_raw / 65535.0
        return temperature, humidity
