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
        print("Ultrasonic -> sensor", sensor.trig.id(), "snow depth (mm):", depth_mm)
    return depths
