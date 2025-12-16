"""Placeholder environment sensor readers."""

def read_air_temperature_C():
    """Stub for reading air temperature in °C."""
    temp = -5.0
    print("Env sensor -> air temp (°C):", temp)
    return temp


def read_relative_humidity():
    """Stub for reading relative humidity in %."""
    humidity = 80.0
    print("Env sensor -> humidity (%):", humidity)
    return humidity


def read_wind_speed_mps():
    """Stub for reading wind speed in m/s."""
    speed = 3.0
    print("Env sensor -> wind speed (m/s):", speed)
    return speed


def read_wind_direction_deg():
    """Stub for reading wind direction in degrees (0-360)."""
    direction = 180.0
    print("Env sensor -> wind direction (deg):", direction)
    return direction
