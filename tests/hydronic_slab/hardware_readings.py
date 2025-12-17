"""Hardware smoke test that streams real sensor readings over serial prints.

This script is intended to run on the ESP32 with the validated wiring. It
cycles through the ultrasonic sensor first, then SHT3x humidity/ambient
temperature, DS18B20 water temperatures, and finally the FL-608 flow sensor.
Each pass prints a compact line that can be monitored over the serial console
to verify live values.
"""

from tests.hydronic_slab.hardware_io import Clock, Ds18b20Bus, FlowSensor, SHT3xSensor
from tests.hydronic_slab.sensors.flow_sensor import DEFAULT_WINDOW_S, FlowReading
from tests.hydronic_slab.sensors.ultrasonic import measure_all_snow_depths_mm


def collect_readings(
    *,
    clock=None,
    ds_bus=None,
    flow=None,
    sht=None,
    flow_window_s: float = DEFAULT_WINDOW_S,
):
    """Capture one set of readings from all hardware sensors.

    The order mirrors the requested print layout: ultrasonic depths first,
    humidity/ambient temperature second, water temperatures third, and flow
    last. A shared ``Clock`` is optional but allows deterministic timing in
    pytest.
    """

    clk = clock or Clock()
    bus = ds_bus or Ds18b20Bus(clock=clk)
    flow_sensor = flow or FlowSensor(clock=clk)
    sht_sensor = sht or SHT3xSensor(clock=clk)

    depths_mm = measure_all_snow_depths_mm()

    air_temp_c, rh_pct = sht_sensor.read()

    bus.start_conversion()
    water_temps_c = bus.read_all_c(wait=True)

    flow_reading = flow_sensor.measure(window_s=flow_window_s, blocking=True)

    return {
        "depths_mm": depths_mm,
        "air_temp_c": air_temp_c,
        "rh_pct": rh_pct,
        "water_temps_c": water_temps_c,
        "flow": flow_reading,
    }


def _fmt_depths(depths) -> str:
    return ", ".join(f"{d:.1f}" for d in depths)


def _fmt_temps(temps) -> str:
    parts = []
    for name, value in temps.items():
        if value is None:
            parts.append(f"{name}: n/a")
        else:
            parts.append(f"{name}: {value:.2f}C")
    return ", ".join(parts)


def print_readings(sample):
    """Emit a serial-friendly summary in the desired order."""

    depths = sample.get("depths_mm") or []
    air_temp_c = sample.get("air_temp_c")
    rh_pct = sample.get("rh_pct")
    temps = sample.get("water_temps_c") or {}
    flow: FlowReading = sample.get("flow")  # type: ignore[assignment]

    print(f"Ultrasonic snow depths (mm): {_fmt_depths(depths)}")
    print(f"SHT3x ambient -> temp: {air_temp_c:.2f} C, RH: {rh_pct:.2f}%")
    print(f"DS18B20 water temps -> {_fmt_temps(temps)}")
    print(
        "Flow sensor -> pulses: {pulses} | Hz: {hz:.2f} | L/min: {lpm:.2f}"
        .format(pulses=flow.pulses, hz=flow.hz, lpm=flow.lpm)
    )


def run_hardware_test(
    *,
    iterations=None,
    interval_s: float = 2.0,
    clock=None,
    ds_bus=None,
    flow=None,
    sht=None,
):
    """Continuously stream readings with optional iteration and sleep control."""

    clk = clock or Clock()
    count = 0
    while iterations is None or count < iterations:
        sample = collect_readings(clock=clk, ds_bus=ds_bus, flow=flow, sht=sht)
        print_readings(sample)
        count += 1
        clk.sleep(interval_s)


if __name__ == "__main__":  # pragma: no cover - manual hardware run
    print("Starting hardware smoke test. Press Ctrl+C to stop.")
    run_hardware_test()
