"""SHT3x single-shot reader using the validated ESP32 wiring."""

import struct

try:  # MicroPython
    from machine import I2C, Pin
except ImportError:  # pragma: no cover - desktop fallback for pytest
    I2C = Pin = None  # type: ignore

SHT3X_SDA_PIN = 21
SHT3X_SCL_PIN = 22
SHT3X_ADDR = 0x44
SHT3X_SINGLE_SHOT_HIGHREP = b"\x24\x00"
SHT3X_DELAY_S = 0.020


class SHT3xSensor:
    """Single-shot SHT3x helper that mirrors the standalone test script."""

    def __init__(self, *, clock) -> None:
        self.clock = clock
        self._present = False
        if I2C is not None:
            self._i2c = I2C(1, sda=Pin(SHT3X_SDA_PIN), scl=Pin(SHT3X_SCL_PIN), freq=100_000)
            try:  # mirror the live test script's scan + guard
                self._present = SHT3X_ADDR in self._i2c.scan()
            except Exception:  # pragma: no cover - defensive around scan errors
                self._present = False
        else:  # pragma: no cover - host fallback
            self._i2c = None

    @staticmethod
    def _crc_ok(data, crc):
        poly = 0x31
        crc_calc = 0xFF
        for byte in data:
            crc_calc ^= byte
            for _ in range(8):
                if crc_calc & 0x80:
                    crc_calc = ((crc_calc << 1) ^ poly) & 0xFF
                else:
                    crc_calc = (crc_calc << 1) & 0xFF
        return crc_calc == crc

    def read(self):
        if self._i2c is None or not self._present:
            return None, None
        try:
            # Single-shot high-repeatability measurement
            self._i2c.writeto(SHT3X_ADDR, SHT3X_SINGLE_SHOT_HIGHREP)
            self.clock.sleep(SHT3X_DELAY_S)
            raw = self._i2c.readfrom(SHT3X_ADDR, 6)
            t_raw, t_crc, rh_raw, rh_crc = struct.unpack(
                ">HBHB", raw
            )
            if not (self._crc_ok(raw[:2], t_crc) and self._crc_ok(raw[3:5], rh_crc)):
                return None, None
            temp_c = -45.0 + (175.0 * t_raw / 65535.0)
            rh = 100.0 * rh_raw / 65535.0
            return temp_c, rh
        except Exception:  # pragma: no cover - defensive around I2C faults
            return None, None
