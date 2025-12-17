"""Hardware-facing helpers for ESP32 + Mega using real sensor wiring."""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from tests.hydronic_slab.sensors.ds18b20 import (
    DS18B20_CONVERSION_DELAY_S,
    Ds18b20Bus,
)
from tests.hydronic_slab.sensors.flow_sensor import DEFAULT_WINDOW_S, FlowReading, FlowSensor
from tests.hydronic_slab.sensors.sht3x_sensor import SHT3X_DELAY_S, SHT3xSensor

try:  # MicroPython
    from machine import UART
except ImportError:  # pragma: no cover - desktop fallback for pytest
    UART = None  # type: ignore


class Clock:
    """Basic wall clock with injectable sleep for deterministic scheduling."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, dt: float) -> None:
        time.sleep(dt)


class MegaRelayDriver:
    """Drive relays on the Mega over UART using line or char protocols."""

    def __init__(
        self,
        *,
        uart: Optional[UART] = None,
        baudrate: int = 9600,
        protocol: str = "line",
        clock: Optional[Clock] = None,
        command_log: Optional[List[Tuple[float, str]]] = None,
        tx_pin: int = 17,
        rx_pin: int = 16,
    ) -> None:
        self.clock = clock or Clock()
        self.protocol = protocol
        self.command_log = command_log

        if uart is None and UART is not None:
            uart = UART(2, baudrate=baudrate, tx=tx_pin, rx=rx_pin)
        self.uart = uart

    # Low-level helpers -------------------------------------------------
    def _write(self, payload: bytes) -> None:
        if self.uart is not None:
            self.uart.write(payload)

    def _record(self, cmd: str) -> None:
        if self.command_log is not None:
            self.command_log.append((self.clock.now(), cmd))

    def send_line(self, text: str) -> None:
        payload = (text + "\n").encode()
        self._write(payload)
        self._record(text)

    def send_char(self, ch: str) -> None:
        payload = ch.encode()
        self._write(payload)
        self._record(ch)

    # Public relay methods ----------------------------------------------
    def pump(self, on: bool) -> None:
        if self.protocol == "line":
            self.send_line("PUMP:ON" if on else "PUMP:OFF")
        else:
            self.send_char("P" if on else "p")

    def heater(self, on: bool) -> None:
        if self.protocol == "line":
            self.send_line("HEATER:ON" if on else "HEATER:OFF")
        else:
            self.send_char("H" if on else "h")

    def sol_a(self, open: bool) -> None:
        if self.protocol == "line":
            self.send_line("SOL_A:ON" if open else "SOL_A:OFF")
        else:
            self.send_char("A" if open else "a")

    def sol_b(self, open: bool) -> None:
        if self.protocol == "line":
            self.send_line("SOL_B:ON" if open else "SOL_B:OFF")
        else:
            self.send_char("B" if open else "b")

    def actuator(self, cmd: str) -> None:
        cmd = cmd.upper()
        if cmd not in {"UP", "DOWN", "STOP"}:
            raise ValueError(f"Unknown actuator command: {cmd}")
        if self.protocol == "line":
            self.send_line(f"ACT:{cmd}")
        else:
            mapping = {"UP": "U", "DOWN": "D", "STOP": "S"}
            self.send_char(mapping[cmd])


def read_environment(
    *,
    ds_bus: Ds18b20Bus,
    flow: FlowSensor,
    sht: SHT3xSensor,
    clock: Optional[Clock] = None,
    flow_window_s: float = DEFAULT_WINDOW_S,
    blocking_flow: bool = False,
) -> Dict[str, object]:
    """Collect a single environment snapshot with deterministic timing."""

    clk = clock or Clock()
    # kick conversions early so control loops can overlap timing with other work
    ds_bus.start_conversion()
    temps = ds_bus.read_all_c(wait=True)
    flow_reading: FlowReading = flow.measure(window_s=flow_window_s, blocking=blocking_flow)
    air_temp, rh = sht.read()

    return {
        "ts": clk.now(),
        "water_temps_c": temps,
        "flow_hz": flow_reading.hz,
        "flow_lpm": flow_reading.lpm,
        "flow_pulses": flow_reading.pulses,
        "flow_window_s": flow_reading.duration_s,
        "air_temp_c": air_temp,
        "rh_pct": rh,
        "latency_s": DS18B20_CONVERSION_DELAY_S + SHT3X_DELAY_S,
    }


__all__ = [
    "Clock",
    "MegaRelayDriver",
    "Ds18b20Bus",
    "FlowSensor",
    "SHT3xSensor",
    "read_environment",
]
