"""Integration-style checks for the hardware IO helpers.

These tests run fully in simulation using FakeClock/FakeRelayDriver so timing
and command ordering can be asserted without physical hardware.
"""

from __future__ import annotations

from typing import List, Tuple

from tests.hydronic_slab.hardware_io import Clock, MegaRelayDriver


class FakeClock(Clock):
    def __init__(self, start: float = 0.0):
        self._t = start
        self.slept: List[float] = []

    def now(self) -> float:
        return self._t

    def sleep(self, dt: float) -> None:
        self.slept.append(dt)
        self._t += dt


class FakeRelayDriver(MegaRelayDriver):
    def __init__(self, *, clock: Clock, protocol: str = "line"):
        self.sent: List[Tuple[float, str]] = []
        super().__init__(uart=None, protocol=protocol, clock=clock, command_log=self.sent)

    def _write(self, payload: bytes) -> None:
        # Override to avoid UART dependency; the base class already logs.
        return None


def _run_tilted_cycle(clock: FakeClock, relays: FakeRelayDriver, period_s: float = 10.0) -> float:
    cycle_start = clock.now()
    relays.actuator("UP")
    clock.sleep(1.0)  # settle to target angle
    relays.actuator("STOP")
    relays.pump(True)
    relays.heater(True)
    clock.sleep(2.5)  # melt window
    relays.heater(False)
    relays.pump(False)
    remaining = period_s - (clock.now() - cycle_start)
    if remaining > 0:
        clock.sleep(remaining)
    return clock.now() - cycle_start


def _run_energy_cycle(clock: FakeClock, relays: FakeRelayDriver, period_s: float = 10.0) -> float:
    cycle_start = clock.now()
    relays.actuator("STOP")  # ensure non-tilted
    relays.pump(True)
    clock.sleep(1.0)
    relays.heater(True)
    clock.sleep(1.0)
    relays.heater(False)
    relays.pump(False)
    remaining = period_s - (clock.now() - cycle_start)
    if remaining > 0:
        clock.sleep(remaining)
    return clock.now() - cycle_start


def test_tilt_then_energy_command_order_and_schedule():
    clock = FakeClock()
    relays = FakeRelayDriver(clock=clock)

    dur1 = _run_tilted_cycle(clock, relays)
    dur2 = _run_energy_cycle(clock, relays)

    commands = [c for _, c in relays.sent]
    assert commands == [
        "ACT:UP",
        "ACT:STOP",
        "PUMP:ON",
        "HEATER:ON",
        "HEATER:OFF",
        "PUMP:OFF",
        "ACT:STOP",
        "PUMP:ON",
        "HEATER:ON",
        "HEATER:OFF",
        "PUMP:OFF",
    ]

    # Ensure actuator directions are not mixed without a stop in between.
    for i in range(len(commands) - 1):
        if commands[i] == "ACT:UP":
            assert commands[i + 1] == "ACT:STOP"

    # Heater must never be on if pump is off within a cycle.
    heater_indices = [i for i, c in enumerate(commands) if c.startswith("HEATER:ON")]
    for idx in heater_indices:
        assert any(j < idx and commands[j] == "PUMP:ON" for j in range(len(commands)))
        assert any(j > idx and commands[j] == "PUMP:OFF" for j in range(idx, len(commands)))

    # Timing: each cycle should honour the 10s period despite waits.
    assert dur1 == 10.0
    assert dur2 == 10.0
    assert clock.now() == 20.0

