"""DS18B20 sensor bus helper for ESP32 (1-Wire on GPIO4)."""

from __future__ import annotations

from typing import Dict, List, Optional

try:  # MicroPython
    from machine import Pin
    import onewire
    import ds18x20
except ImportError:  # pragma: no cover - desktop fallback for pytest
    Pin = onewire = ds18x20 = None  # type: ignore

DS18B20_DATA_PIN = 4
# 12-bit conversions take ~750 ms
DS18B20_CONVERSION_DELAY_S = 0.75


class Ds18b20Bus:
    """Two-phase conversion helper that keeps timing testable."""

    def __init__(self, data_pin: int = DS18B20_DATA_PIN, *, clock) -> None:
        self.clock = clock
        self._last_conversion_start: Optional[float] = None
        self._roms: List[bytes] = []
        if ds18x20 is not None and onewire is not None:
            self._ow = onewire.OneWire(Pin(data_pin))
            self._ds = ds18x20.DS18X20(self._ow)
            self._roms = list(self._ds.scan())
        else:  # pragma: no cover - used in host tests
            self._ow = self._ds = None

    def scan_roms(self) -> List[bytes]:
        if self._ds is None:
            return list(self._roms)
        self._roms = list(self._ds.scan())
        return self._roms

    def start_conversion(self) -> None:
        if self._ds is None:
            self._last_conversion_start = self.clock.now()
            return
        self._ds.convert_temp()
        self._last_conversion_start = self.clock.now()

    def _ensure_conversion_complete(self) -> None:
        if self._last_conversion_start is None:
            self.start_conversion()
        if self._last_conversion_start is None:
            return
        remaining = DS18B20_CONVERSION_DELAY_S - (self.clock.now() - self._last_conversion_start)
        if remaining > 0:
            self.clock.sleep(remaining)

    def read_all_c(self, *, wait: bool = True) -> Dict[str, Optional[float]]:
        if wait:
            self._ensure_conversion_complete()
        if self._ds is None:
            return {str(idx): None for idx, _ in enumerate(self._roms)}
        temps: Dict[str, Optional[float]] = {}
        for rom in self._roms:
            temps[rom.hex()] = self._ds.read_temp(rom)
        return temps

    def read_named_c(self, name_map: Dict[str, str], *, wait: bool = True) -> Dict[str, Optional[float]]:
        raw = self.read_all_c(wait=wait)
        return {name_map.get(rom, rom): temp for rom, temp in raw.items()}
