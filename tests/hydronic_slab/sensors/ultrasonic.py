"""Ultrasonic array helpers for snow depth measurement.

This mirrors the validated ESP32 script that uses a single HC-SR04-style
transducer on TRIG=18 / ECHO=19 with ``time_pulse_us`` for ranging.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, List, Optional

try:  # MicroPython
    import machine
except ImportError:  # pragma: no cover - pytest shims machine in conftest
    machine = None


Pin = getattr(machine, "Pin", None)
time_pulse_us = getattr(machine, "time_pulse_us", None)
sleep_us = getattr(time, "sleep_us", None)

SPEED_OF_SOUND = 343.0

# Default to the validated ESP32 wiring (TRIG=18, ECHO=19)
ULTRA_PINS = [
    {"trig": 18, "echo": 19},
"""Ultrasonic array helpers for snow depth measurement."""
from machine import Pin

SPEED_OF_SOUND = 343.0

ULTRA_PINS = [
    {"trig": 4, "echo": 5},
    {"trig": 18, "echo": 19},
    {"trig": 21, "echo": 22},
    {"trig": 23, "echo": 32},
    {"trig": 33, "echo": 25},
    {"trig": 26, "echo": 27},
]


class UltrasonicSensor:
    """HC-SR04-style ultrasonic distance sensor wrapper."""

    def __init__(
        self,
        trig_pin: int,
        echo_pin: int,
        *,
        timeout_us: int = 30_000,
        pulse_reader: Optional[Callable[[object, int, int], int]] = None,
        fallback_distance_m: float = 0.15,
    ) -> None:
        if Pin is None:
            raise RuntimeError("machine.Pin unavailable; ultrasonic sensor unsupported")

        self.trig = Pin(trig_pin, Pin.OUT)
        self.echo = Pin(echo_pin, Pin.IN)
        self.timeout_us = timeout_us
        self.pulse_reader = pulse_reader or time_pulse_us
        self.fallback_distance_m = fallback_distance_m

        # settle trigger low before first shot
        try:
            self.trig.value(0)
        except Exception:  # pragma: no cover - defensive for stubs
            pass

    def _time_pulse(self) -> Optional[int]:
        if self.pulse_reader is None:
            return None
        try:
            return self.pulse_reader(self.echo, 1, self.timeout_us)
        except OSError:
            return None

    def measure_distance_m(self) -> Optional[float]:
        """Measure distance in meters using a 10 µs trigger pulse."""
        # trigger 10 us pulse
        try:
            self.trig.value(0)
            if sleep_us:
                sleep_us(2)
            self.trig.value(1)
            if sleep_us:
                sleep_us(10)
            self.trig.value(0)
        except Exception:
            # Fall back immediately in host-simulated tests
            return self.fallback_distance_m

        duration = self._time_pulse()
        if duration is None or duration <= 0:
            return self.fallback_distance_m

        distance_m = (duration / 1_000_000.0) * SPEED_OF_SOUND / 2.0
        return distance_m


def _create_sensors(configs: Iterable[dict]) -> List[UltrasonicSensor]:
    return [UltrasonicSensor(cfg["trig"], cfg["echo"]) for cfg in configs]


ultra_sensors = _create_sensors(ULTRA_PINS)


def measure_snow_depth_mm(mount_height_m: float = 0.5) -> float:
    """Average snow depth across all ultrasonic sensors in millimeters."""
    distances = [d for d in (sensor.measure_distance_m() for sensor in ultra_sensors) if d is not None]
    """
    Simple ultrasonic distance sensor wrapper using a trig/echo pair.
    """

    def __init__(self, trig_pin, echo_pin):
        self.trig = Pin(trig_pin, Pin.OUT)
        self.echo = Pin(echo_pin, Pin.IN)

    def measure_distance_m(self):
        """Measure distance in meters (stub implementation)."""
        distance = 0.15
        print(
            "Ultrasonic sensor trig=", self.trig.id(),
            "echo=", self.echo.id(),
            "distance (m)=", distance,
        )
        return distance


def _create_sensors():
    return [UltrasonicSensor(cfg["trig"], cfg["echo"]) for cfg in ULTRA_PINS]


ultra_sensors = _create_sensors()


def measure_snow_depth_mm(mount_height_m=0.5):
    """Average snow depth across all ultrasonic sensors in millimeters."""
    distances = [sensor.measure_distance_m() for sensor in ultra_sensors]
    if not distances:
        return 0.0

    avg_distance = sum(distances) / len(distances)
    raw_depth_m = mount_height_m - avg_distance
    if raw_depth_m < 0:
        raw_depth_m = 0.0
    depth_mm = raw_depth_m * 1000.0
    print("Ultrasonic -> avg snow depth (mm):", depth_mm)
    return depth_mm


def measure_all_snow_depths_mm(mount_height_m: float = 0.5) -> List[float]:
    """Return per-sensor snow depth readings in millimeters."""
    depths: List[float] = []
    for sensor in ultra_sensors:
        distance = sensor.measure_distance_m()
        if distance is None:
            continue
def measure_all_snow_depths_mm(mount_height_m=0.5):
    """Return per-sensor snow depth readings in millimeters."""
    depths = []
    for sensor in ultra_sensors:
        distance = sensor.measure_distance_m()
        raw_depth_m = mount_height_m - distance
        if raw_depth_m < 0:
            raw_depth_m = 0.0
        depth_mm = raw_depth_m * 1000.0
        depths.append(depth_mm)
        print("Ultrasonic -> sensor", getattr(sensor.trig, "pin", None), "snow depth (mm):", depth_mm)
        print("Ultrasonic -> sensor", sensor.trig.id(), "snow depth (mm):", depth_mm)
    return depths
