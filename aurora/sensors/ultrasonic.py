"""Ultrasonic distance helpers (shared TRIG, separate ECHOs)."""

import time
from typing import List, Optional

import aurora.config as config

SOUND_CM_PER_US = 0.0343 / 2


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


class UltrasonicArray:
    def __init__(self, trig_pin=config.ULTRASONIC_TRIG, echo_pins=None):
        self.trig_pin = trig_pin
        self.echo_pins = echo_pins or list(config.ULTRASONIC_ECHOS)

    def _read_echo(self, echo_pin):
        # Placeholder: in MicroPython use machine.Pin + time_pulse_us
        return None

    def _clamp_range(self, value):
        if value is None:
            return None
        if value < config.ULTRASONIC_MIN_CM or value > config.ULTRASONIC_MAX_CM:
            return None
        return value

    def read_all(self) -> List[Optional[float]]:
        readings = []
        for echo in self.echo_pins:
            distance = None
            for _ in range(config.ULTRASONIC_RETRIES):
                raw = self._read_echo(echo)
                if raw is None:
                    _sleep_ms(config.ULTRASONIC_PING_GAP_MS)
                    continue
                distance = raw * SOUND_CM_PER_US
                break
            readings.append(self._clamp_range(distance))
            _sleep_ms(config.ULTRASONIC_PING_GAP_MS)
        return readings

    def depths(self, mount_height_cm=config.MOUNT_HEIGHT_CM):
        depths = []
        for dist in self.read_all():
            if dist is None:
                depths.append(None)
                continue
            depth = max(0.0, min(mount_height_cm, mount_height_cm - dist))
            depths.append(depth)
        valid = [d for d in depths if d is not None]
        avg_depth = sum(valid) / len(valid) if valid else None
        return depths, avg_depth
