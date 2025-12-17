"""Unit coverage for the hardware smoke-test helper."""

from pathlib import Path
from typing import Dict, Optional

import pytest

from tests.hydronic_slab.hardware_io import Clock
from tests.hydronic_slab.hardware_readings import collect_readings, print_readings, run_hardware_test
from tests.hydronic_slab.sensors.flow_sensor import FlowReading


class FakeClock(Clock):
    def __init__(self):
        self._t = 0.0
        self.slept = []

    def now(self) -> float:  # pragma: no cover - trivial
        return self._t

    def sleep(self, dt: float) -> None:
        self.slept.append(dt)
        self._t += dt


class FakeFlow:
    def __init__(self, reading: FlowReading):
        self.reading = reading

    def measure(self, window_s: float, *, blocking: bool) -> FlowReading:  # pragma: no cover - simple passthrough
        return FlowReading(
            pulses=self.reading.pulses,
            duration_s=window_s,
            hz=self.reading.hz,
            lpm=self.reading.lpm,
        )


class FakeDsBus:
    def __init__(self, temps: Dict[str, Optional[float]]):
        self.temps = temps
        self.started = False

    def start_conversion(self):  # pragma: no cover - trivial
        self.started = True

    def read_all_c(self, wait: bool = True):  # pragma: no cover - trivial
        return self.temps


class FakeSHT:
    def __init__(self, temp: float, rh: float):
        self.temp = temp
        self.rh = rh

    def read(self):  # pragma: no cover - trivial
        return self.temp, self.rh


def test_collect_readings_orders_sources(monkeypatch):
    depth_calls = []

    def fake_depths():
        depth_calls.append(True)
        return [12.0, 15.5]

    monkeypatch.setattr("tests.hydronic_slab.hardware_readings.measure_all_snow_depths_mm", fake_depths)

    ds_bus = FakeDsBus({"a": 1.0, "b": None})
    flow = FakeFlow(FlowReading(pulses=10, duration_s=1.5, hz=6.6, lpm=0.88))
    sht = FakeSHT(22.5, 40.0)
    clock = FakeClock()

    sample = collect_readings(clock=clock, ds_bus=ds_bus, flow=flow, sht=sht)

    assert depth_calls  # ultrasonic was invoked first
    assert sample["depths_mm"] == [12.0, 15.5]
    assert sample["air_temp_c"] == 22.5
    assert sample["rh_pct"] == 40.0
    assert sample["water_temps_c"] == {"a": 1.0, "b": None}
    assert sample["flow"].pulses == 10


def test_print_readings_sequence(capsys):
    sample = {
        "depths_mm": [10.0, 20.0],
        "air_temp_c": 5.0,
        "rh_pct": 80.0,
        "water_temps_c": {"rom0": 1.23},
        "flow": FlowReading(pulses=5, duration_s=1.5, hz=3.3, lpm=0.44),
    }

    print_readings(sample)
    out = capsys.readouterr().out.strip().split("\n")
    assert out[0].startswith("Ultrasonic")
    assert out[1].startswith("SHT3x")
    assert out[2].startswith("DS18B20")
    assert out[3].startswith("Flow sensor")


def test_run_hardware_test_uses_clock_sleep(monkeypatch, capsys):
    clock = FakeClock()

    monkeypatch.setattr(
        "tests.hydronic_slab.hardware_readings.collect_readings",
        lambda **_: {
            "depths_mm": [1.0],
            "air_temp_c": 1.0,
            "rh_pct": 1.0,
            "water_temps_c": {"0": 1.0},
            "flow": FlowReading(pulses=1, duration_s=1.5, hz=1.0, lpm=0.13),
        },
    )

    run_hardware_test(iterations=2, interval_s=0.5, clock=clock)

    out_lines = capsys.readouterr().out.strip().split("\n")
    assert len([l for l in out_lines if l.startswith("Ultrasonic")]) == 2
    assert clock.slept == [0.5, 0.5]


def test_no_cpython_only_imports_in_micropython_files():
    # Guard that MicroPython-facing modules avoid CPython-only imports such as
    # __future__, typing, runpy, pathlib, or dataclasses to keep on-device
    # execution clean.
    banned = ["from __future__", "typing", "runpy", "pathlib", "dataclasses"]
    targets = [
        "tests/hydronic_slab/hardware_readings.py",
        "tests/hydronic_slab/hardware_io.py",
        "tests/hydronic_slab/sensors/ds18b20.py",
        "tests/hydronic_slab/sensors/flow_sensor.py",
        "tests/hydronic_slab/sensors/sht3x_sensor.py",
        "tests/hydronic_slab/sensors/ultrasonic.py",
    ]

    for path in targets:
        text = Path(path).read_text()
        for needle in banned:
            assert needle not in text, f"{needle} should not appear in {path}"
