"""Unit checks for the ultrasonic snow-depth helpers."""

from math import isclose

from tests.hydronic_slab.sensors import ultrasonic


def test_ultrasonic_converts_pulse_to_distance():
    sensor = ultrasonic.UltrasonicSensor(
        18,
        19,
        pulse_reader=lambda *_: 1_000,  # 1000 µs high pulse
    )
    distance_m = sensor.measure_distance_m()
    assert distance_m is not None
    # distance = (t * speed) / 2
    assert isclose(distance_m, (0.001 * ultrasonic.SPEED_OF_SOUND) / 2, rel_tol=1e-3)


def test_snow_depth_uses_fallback_when_no_echo(monkeypatch):
    # Force the global sensors list to use a predictable fallback distance.
    sensor = ultrasonic.UltrasonicSensor(
        18,
        19,
        pulse_reader=lambda *_: -1,
        fallback_distance_m=0.15,
    )
    monkeypatch.setattr(ultrasonic, "ultra_sensors", [sensor])
    depth_mm = ultrasonic.measure_snow_depth_mm(mount_height_m=0.5)
    assert depth_mm == (0.5 - 0.15) * 1000

