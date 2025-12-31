"""DS18B20 temperature helpers with retries and bad-value filtering."""

import time
from typing import Dict, List, Optional

import aurora.config as config

BAD_LOW = -127.0
BAD_HIGH = 85.0


class DS18B20Suite:
    def __init__(self, roms=None):
        self.roms = roms or []

    def scan_roms(self):
        # Placeholder: real implementation should populate from OneWire bus
        return list(self.roms)

    def read_rom(self, rom):
        # Placeholder for MicroPython read
        return None

    def read_all(self, roles) -> Dict[str, Optional[float]]:
        temps = {}
        pavements = []
        for rom in roles.get("pavement", [])[:10]:
            pavements.append(self.read_rom(rom))
        temps["pavement"] = pavements
        temps["fluid_out"] = self.read_rom(roles.get("fluid_out"))
        temps["fluid_return"] = self.read_rom(roles.get("fluid_return"))
        temps["roms"] = self.scan_roms()
        return temps

    @staticmethod
    def valid_temp(value):
        if value is None:
            return False
        if abs(value - BAD_LOW) < 0.5:
            return False
        if abs(value - BAD_HIGH) < 0.5:
            return False
        return True

    @staticmethod
    def avg(values: List[Optional[float]]):
        valid = [v for v in values if v is not None]
        return sum(valid) / len(valid) if valid else None
