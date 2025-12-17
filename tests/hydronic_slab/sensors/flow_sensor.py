"""Digiten FL-608 flow sensor helper with IRQ counting and glitch filter.

The defaults mirror the validated live test script that arms an interrupt on
GPIO5 with a 2 ms glitch filter, a 1.5 s measurement window, and a calibration
constant of ~450 pulses per liter (about 7.5 Hz per L/min).
"""

import time

try:  # MicroPython
    from machine import Pin
except ImportError:  # pragma: no cover - desktop fallback for pytest
    Pin = None  # type: ignore

FLOW_SENSOR_PIN = 5
FLOW_GLITCH_US = 2000  # ignore pulses faster than 2 ms apart
DEFAULT_WINDOW_S = 1.5
DEFAULT_PULSES_PER_LITER = 450.0


class FlowReading:
    def __init__(self, pulses, duration_s, hz, lpm):
        self.pulses = pulses
        self.duration_s = duration_s
        self.hz = hz
        self.lpm = lpm


def _ticks_us() -> int:
    try:
        return time.ticks_us()  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - desktop fallback
        return int(time.monotonic() * 1_000_000)


def _ticks_diff(new: int, old: int) -> int:
    try:
        return time.ticks_diff(new, old)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - desktop fallback
        return new - old


class FlowSensor:
    """IRQ-driven pulse counter with non-blocking rate calculations."""

    def __init__(
        self,
        pin: int = FLOW_SENSOR_PIN,
        *,
        clock,
        pulses_per_liter: float = DEFAULT_PULSES_PER_LITER,
        attach_irq: bool = True,
    ) -> None:
        self.clock = clock
        self.pulses_per_liter = pulses_per_liter
        self._count = 0
        self._last_pulse_us = None
        self._last_rate_hz: float = 0.0
        self._last_rate_time = None

        if Pin is not None and attach_irq:
            # Mirror the standalone script: GPIO5, pull-up enabled, falling-edge IRQ.
            self._pin = Pin(pin, Pin.IN, Pin.PULL_UP)
            self._pin.irq(trigger=Pin.IRQ_FALLING, handler=self._irq_handler)
        else:  # pragma: no cover - host fallback
            self._pin = None

    # IRQ callback --------------------------------------------------
    def _irq_handler(self, _pin=None):  # pragma: no cover - hardware only
        now_us = _ticks_us()
        if self._last_pulse_us is not None:
            delta = _ticks_diff(now_us, self._last_pulse_us)
            if delta < FLOW_GLITCH_US:
                return
        self._last_pulse_us = now_us
        self._count += 1

    # Helpers for tests ---------------------------------------------
    def simulate_pulses(self, n: int, spacing_s: float = 0.1) -> None:
        for _ in range(n):
            self._count += 1
            self.clock.sleep(spacing_s)

    # Rate calculation ----------------------------------------------
    def measure(self, window_s: float = DEFAULT_WINDOW_S, *, blocking: bool = False) -> FlowReading:
        if blocking:
            start = self.clock.now()
            start_count = self._count
            self.clock.sleep(window_s)
            elapsed = self.clock.now() - start
            pulses = self._count - start_count
        else:
            if self._last_rate_time is None:
                self._last_rate_time = self.clock.now()
                return FlowReading(pulses=0, duration_s=0.0, hz=0.0, lpm=0.0)
            elapsed = self.clock.now() - self._last_rate_time
            if elapsed < window_s:
                return FlowReading(
                    pulses=self._count,
                    duration_s=elapsed,
                    hz=self._last_rate_hz,
                    lpm=(self._last_rate_hz * 60.0) / self.pulses_per_liter
                    if self.pulses_per_liter
                    else 0.0,
                )
            pulses = self._count
            self._count = 0
            self._last_rate_time = self.clock.now()

        hz = pulses / elapsed if elapsed > 0 else 0.0
        self._last_rate_hz = hz
        lpm = (hz * 60.0) / self.pulses_per_liter if self.pulses_per_liter else 0.0
        return FlowReading(pulses=pulses, duration_s=elapsed, hz=hz, lpm=lpm)

    def measure_hz(self, window_s: float = DEFAULT_WINDOW_S, *, blocking: bool = False) -> float:
        return self.measure(window_s=window_s, blocking=blocking).hz

    def measure_lpm(self, window_s: float = DEFAULT_WINDOW_S, *, blocking: bool = False) -> float:
        return self.measure(window_s=window_s, blocking=blocking).lpm
